from django.utils.decorators import available_attrs
from functools import wraps
import logging
import types
import traceback

def task():
    from django_ztask.conf import settings
    import zmq

    def wrapper(func):
        function_name = '%s.%s' % (func.__module__, func.__name__)
        
        logger = logging.getLogger('ztask')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        #logger.info('Registered task: %s' % function_name)
        
        from django_ztask.context import shared_context as context

        socket = context.socket(zmq.PUSH)
        socket.connect(settings.ZTASKD_URL)

        @wraps(func)
        def _func(*args, **kwargs):
            after = kwargs.pop('__ztask_after', 0)
            
            # check if the server is alive
            alive_socket = context.socket(zmq.REQ)
            alive_socket.connect(settings.ZTASKD_ALIVE_URL)
            poll = zmq.Poller()
            poll.register(alive_socket, zmq.POLLIN)
            request = 'ping'
            alive_socket.send(request)
            socks = dict(poll.poll(settings.ZTASKD_ALIVE_TIMEOUT))
            if socks.get(alive_socket) == zmq.POLLIN:
                reply = alive_socket.recv()
            else:
                # consider the server dead
                alive_socket.setsockopt(zmq.LINGER, 0)
                alive_socket.close()
                poll.unregister(alive_socket)
                logger.info('Running %s in-process because the ztaskd server is not responding' % function_name)
                func(*args, **kwargs)
                return

            if settings.ZTASKD_DISABLED:
                try:
                    socket.send_pyobj(('ztask_log', ('Would have called but ZTASKD_DISABLED is True', function_name), None, 0))
                except:
                    logger.info('Would have sent %s but ZTASKD_DISABLED is True' % function_name)
                return
            elif settings.ZTASKD_ALWAYS_EAGER:
                logger.info('Running %s in ZTASKD_ALWAYS_EAGER mode' % function_name)
                if after > 0:
                    logger.info('Ignoring timeout of %d seconds because ZTASKD_ALWAYS_EAGER is set' % after)
                func(*args, **kwargs)
            else:
                try:
                    socket.send_pyobj((function_name, args, kwargs, after))
                except Exception, e:
                    if after > 0:
                        logger.info('Ignoring timeout of %s seconds because function is being run in-process' % after)
                    func(*args, **kwargs)

        def _func_delay(*args, **kwargs):
            try:
                socket.send_pyobj(('ztask_log', ('.delay is deprecated... use.async instead', function_name), None, 0))
            except:
                pass
            _func(*args, **kwargs)
            
        def _func_after(*args, **kwargs):
            try:
                after = args[0]
                if type(after) != types.IntType:
                    raise TypeError('The first argument of .after must be an integer representing seconds to wait')
                kwargs['__ztask_after'] = after
                _func(*args[1:], **kwargs)
            except Exception, e:
                logger.error('Error adding delayed task:\n%s' % e)
                traceback.print_exc(e)
        
        setattr(func, 'async', _func)
        setattr(func, 'delay', _func_delay)
        setattr(func, 'after', _func_after)
        return func
    
    return wrapper
