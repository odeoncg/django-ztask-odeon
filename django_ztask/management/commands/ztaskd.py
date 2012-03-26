from django.core.management.base import BaseCommand
from django.utils import autoreload
from django.conf import settings as main_settings
from django import db
from django_ztask.models import *
from django_ztask.conf import settings
import zmq
from zmq.eventloop import ioloop
from optparse import make_option
import sys
import traceback
import logging
import pickle
import datetime, time
import os
import signal
from pprint import pprint
import multiprocessing
from django.utils.daemonize import become_daemon

STOP_REQUESTED = False
logger = None
io_loop = None
pool = None

def signal_handler(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True

def call_function(task_id, function_name=None, args=None, kwargs=None):
    try:
        if not function_name:
            try:
                task = Task.objects.get(pk=task_id)
                function_name = task.function_name
                args = pickle.loads(str(task.args))
                kwargs = pickle.loads(str(task.kwargs))
            except Exception, e:
                logger.info('Could not get task with id %s:\n%s' % (task_id, e))
                return
            
        logger.info('Calling %s' % function_name)
        parts = function_name.split('.')
        module_name = '.'.join(parts[:-1])
        member_name = parts[-1]
        if not module_name in sys.modules:
            __import__(module_name)
        function = getattr(sys.modules[module_name], member_name)
        function(*args, **kwargs)
        logger.info('Called %s successfully' % function_name)
        Task.objects.get(pk=task_id).delete()
    except Exception, e:
        logger.error('Error calling %s. Details:\n%s' % (function_name, e))
        try:
            task = Task.objects.get(pk=task_id)
            task.failed = datetime.datetime.utcnow()
            task.last_exception = '%s' % e
            task.save()
            if task.retry_count > 0:
                task.retry_count -= 1
                task.next_attempt = time.time() + settings.ZTASKD_RETRY_AFTER
                task.save()
                call_function(task.pk)
        except Exception, e2:
            logger.error('Error capturing exception in call_function. Details:\n%s' % e2)
        traceback.print_exc(e)
    
def replay_task_callback_factory(*args, **kwargs):
    return lambda: pool.apply_async(call_function, args, kwargs)

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-f', '--logfile', action='store', dest='logfile', default=None, help='Tells ztaskd where to log information. Leaving this blank logs to stderr'),
        make_option('-l', '--loglevel', action='store', dest='loglevel', default='info', help='Tells ztaskd what level of information to log'),
        make_option('--pidfile', action='store', dest='pidfile', default=None, help='PID file'),
        make_option('--noreload', action='store_false', dest='use_reloader', default=True, help='Tells Django to NOT use the auto-reloader'),
        make_option('--daemonize', action='store_true', dest='daemonize', default=False, help='Become a daemon'),
        make_option('--replayfailed', action='store_true', dest='replay_failed', default=False, help='Replays all failed calls in the db'),
        make_option('--workers', action='store', dest='workers', default=None, help='Number of worker processes. Defaults to %d' % multiprocessing.cpu_count()),
        make_option('--stop', action='store_true', dest='stop_requested', default=False, help='stop the ztaskd server indicated by pidfile'),
    )
    args = ''
    help = 'Start the ztaskd server'
    func_cache = {}

    def _request_stop(self):
        if not self.pidfile:
            print "error: no pidfile specified"
            exit(1)
        try:
            pid = int(open(self.pidfile).read())
        except:
            print 'error: missing pidfile'
        try:
            os.kill(pid, signal.SIGTERM)
            while(True):
                time.sleep(1)
                if not os.path.exists(self.pidfile):
                    break
        except: #process does not exist
            pass
    
    def handle(self, *args, **options):
        self._setup_logger(options['logfile'], options['loglevel'])
        replay_failed = options['replay_failed']
        use_reloader = options['use_reloader']
        self.pidfile = options['pidfile']
        self.workers = options['workers']
        if self.workers:
            self.workers = int(self.workers)
        else:
            # avoid a value of 0
            self.workers = None
        self.stop_check_interval = 1
        stop_requested = options['stop_requested']
        if stop_requested:
            self._request_stop()
            return
        signal.signal(signal.SIGTERM, signal_handler)
        self.daemonize = options['daemonize']
        if self.daemonize:
            become_daemon()
        # close the db connection before spawning the pool workers so each gets a new one
        db.close_connection()
        global pool
        pool = multiprocessing.Pool(self.workers)
        if use_reloader:
            autoreload.main(lambda: self._handle(use_reloader, replay_failed))
        else:
            self._handle(use_reloader, replay_failed)
    
    def _write_pidfile(self):
        fp = open(self.pidfile, 'w')
        fp.write("%d\n" % os.getpid())
        fp.close()

    def _stop(self):
        if STOP_REQUESTED:
            # close the sockets
            self.alive_socket.close()
            self.socket.close()
            # close the pool and wait for all the workers to complete
            pool.close()
            pool.join()
            io_loop.stop()
            while(io_loop.running()):
                time.sleep(1)
            logger.info("Server stoped with SIGTERM")
            os.remove(self.pidfile)
        else:
            io_loop.add_timeout(datetime.timedelta(seconds=self.stop_check_interval), self._stop)

    def _handle(self, use_reloader, replay_failed):
        logger.info("%sServer starting on %s." % ('Development ' if use_reloader else '', settings.ZTASKD_URL))
        self._write_pidfile()
        self._on_load()
        
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(settings.ZTASKD_URL)
        self.alive_socket = self.context.socket(zmq.REP)
        self.alive_socket.bind(settings.ZTASKD_ALIVE_URL)
        global io_loop
        
        def _queue_handler(socket, *args, **kwargs):
            try:
                function_name, args, kwargs, after = socket.recv_pyobj()
                if function_name == 'ztask_log':
                    logger.warn('%s: %s' % (args[0], args[1]))
                    return
                task = Task.objects.create(
                    function_name=function_name, 
                    args=pickle.dumps(args), 
                    kwargs=pickle.dumps(kwargs), 
                    retry_count=settings.ZTASKD_RETRY_COUNT,
                    next_attempt=time.time() + after
                )
                
                if after:
                    ioloop.DelayedCallback(replay_task_callback_factory(task.pk, function_name=function_name, args=args, kwargs=kwargs), after * 1000, io_loop=io_loop).start()
                else:
                    pool.apply_async(call_function, [task.pk], dict(function_name=function_name, args=args, kwargs=kwargs))
            except Exception, e:
                logger.error('Error setting up function. Details:\n%s' % e)
                traceback.print_exc(e)
        
        def _alive_handler(alive_socket, *args, **kwargs):
            request = alive_socket.recv()
            reply = 'pong'
            alive_socket.send(reply)

        # Reload tasks if necessary
        if replay_failed:
            replay_tasks = Task.objects.all().order_by('created')
        else:
            replay_tasks = Task.objects.filter(retry_count__gt=0).order_by('created')
        for task in replay_tasks:
            logger.info('replaying task %s' % task.pk)
            if task.next_attempt < time.time():
                after = settings.ZTASKD_RETRY_AFTER
            else:
                after = task.next_attempt - time.time()
            ioloop.DelayedCallback(replay_task_callback_factory(task.pk), after * 1000, io_loop=io_loop).start()
        
        io_loop = ioloop.IOLoop.instance()
        io_loop.add_handler(self.socket, _queue_handler, io_loop.READ)
        io_loop.add_handler(self.alive_socket, _alive_handler, io_loop.READ)
        io_loop.add_timeout(datetime.timedelta(seconds=self.stop_check_interval), self._stop)
        io_loop.start()
    
    def _setup_logger(self, logfile, loglevel):
        LEVELS = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }
        
        global logger
        logger = logging.getLogger('ztaskd')
        logger.setLevel(LEVELS[loglevel.lower()])
        if logfile:
            handler = logging.FileHandler(logfile, delay=True)
        else:
            handler = logging.StreamHandler()
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    def _on_load(self):
        for callable_name in settings.ZTASKD_ON_LOAD:
            logger.info("ON_LOAD calling %s" % callable_name)
            parts = callable_name.split('.')
            module_name = '.'.join(parts[:-1])
            member_name = parts[-1]
            if not module_name in sys.modules:
                __import__(module_name)
            callable_fn = getattr(sys.modules[module_name], member_name)
            callable_fn()
            
    



