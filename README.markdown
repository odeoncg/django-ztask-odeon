About
=====

django-ztask is a lightweight asynchronous task queue for Django based on zeromq.
It appeared as a [quick hack](http://www.zeromq.org/story:3) but proved to be a simple, solid and highly hackable alternative to [celery](http://celeryproject.org/).

This is a fork of of the [original project](https://github.com/dmgctrl/django-ztask) which seems unmaintained for almost an year.

New features:

- `stop` command and init script helper: `ztask_server.sh`

- parallel processing of tasks

- checking the server status before sending a task (the task is executed in-process if ztaskd is not available)

- daemonize support

Installing
==========

Install the required packages (preferably using your distribution's package manager):

- [zeromq](http://www.zeromq.org)

- [pyzmq](http://www.zeromq.org/bindings:python)

- [South](http://south.aeracode.org/)

Install django-ztask.

Add `django_ztask` to your `INSTALLED_APPS` setting in `settings.py`

    INSTALLED_APPS = (
        ...,
        'django_ztask',
    )

Then apply the South migrations:

    ./manage.py migrate django-ztask
    

Running the server
==================

Run django-ztask using the manage.py command:

    ./manage.py ztaskd


Command-line arguments
----------------------

The `ztaskd` command takes a series of command-line arguments:

- `-f` or `--logfile`
  
  The file to log messages to. By default, all messages are logged
  to `stdout`

- `-l` or `--loglevel`
  
  Choose from the standard `CRITICAL`, `ERROR`, `WARNING`, 
  `INFO`, `DEBUG`, or `NOTSET`. If this argument isn't passed 
  in, `INFO` is used by default.

- `--pidfile`

  The file to write the PID to. Required for stopping the daemon.

- `--noreload`
  
  By default, `ztaskd` will use the built-in Django reloader 
  to reload the server whenever a change is made to a python file. Passing
  in `--noreload` will prevent it from listening for changed files.
  (Good to use in production.)

- `--daemonize`

  Make the server a daemon. Disabled by default.

- `--replayfailed`
  
  If a command has failed more times than allowed in the 
  `ZTASKD_RETRY_COUNT` (see below for more), the task is
  logged as failed. Passing in `--replayfailed` will cause all 
  failed tasks to be re-run.

- `--workers`

  Number of worker processes. Defaults to the number of available CPUs/cores
  as reported by the operating system.

- `--stop`

  Stop the ztaskd instance indicated by `--pidfile`. The pidfile should be
  the same passed as an argument when the ztaskd server was started.
  This command will wait until the server is stopped.

Settings
--------

There are several settings that you can put in your `settings.py` file in 
your Django project. These are the settings and their defaults

    ZTASKD_URL = 'tcp://127.0.0.1:5555'

By default, `ztaskd` will run over TCP, listening on 127.0.0.1 port 5555.

    ZTASKD_ALIVE_URL = 'tcp://127.0.0.1:5556'

The URL on which `ztaskd` listens for 'alive' requests (used by the decorator
to decide whether to send the task or run it in-process).

    ZTASKD_ALIVE_TIMEOUT = 1000

Number of milliseconds to wait for an 'alive' reply. If the timeout is reached and
no reply was received, the server is considered dead.

    ZTASKD_ALWAYS_EAGER = False

If set to `True`, all `.async` and `.after` tasks will be run in-process and
not sent to the `ztaskd` process. Good for task debugging.

    ZTASKD_DISABLED = False

If set, all tasks will be logged, but not executed. This setting is often 
used during testing runs. If you set `ZTASKD_DISABLED` before running 
`python manage.py test`, tasks will be logged, but not executed.

    ZTASKD_RETRY_COUNT = 5

The number of times a task should be reattempted before it is considered failed.

    ZTASKD_RETRY_AFTER = 5

The number, in seconds, to wait in-between task retries. 

    ZTASKD_ON_LOAD = ()
    
This is a list of callables - either classes or functions - that are called when the server first
starts. This is implemented to support several possible Django setup scenarios when launching
`ztask` - for an example, see the section below called **Implementing with Johnny Cache**.


Running in production
---------------------

The recommended way to run ztaskd in production is through the `ztask_server.sh` shell script:

    ./ztask_server.sh start
    ./ztask_server.sh restart
    ./ztask_server.sh stop

Make sure that the logging and pidfile directories exist and can be written into by the user
running the script.

The `stop` command (and implicitly `restart`) is synchronous. Usually this is what you want when
stopping the server: wait until the server has been stopped. Restarts, however, can be asynchronous
(like when restarting ztaskd from a git hook) and in this case we would run the script in background:

    ./ztask_server.sh restart &

You can run many 'restart' jobs in parallel. There's file locking to ensure proper behavior.

Making functions into tasks
===========================

Decorators and function extensions make tasks able to run. 
Unlike some solutions, tasks can be in any file anywhere. 
When the file is imported, `ztaskd` will register the task for running.

**Important note: all functions and their arguments must be able to be pickled.**

([Read more about pickling here](http://docs.python.org/tutorial/inputoutput.html#the-pickle-module))

It is a recommended best practice that instead of passing a Django model object 
to a task, you instead pass along the model's ID or primary key, and re-get 
the object in the task function.

The @task Decorator
-------------------

    from django_ztask.decorators import task

The `@task()` decorator will turn any normal function in to a 
`django_ztask` task if called using one of the function extensions.

Function extensions
-------------------

Any function can be called in one of three ways:

- `func(*args, *kwargs)`

  Calling a function normally will bypass the decorator and call the function directly

- `func.async(*args, **kwargs)`

  Calling a function with `.async` will cause the function task to be called asynchronously 
  on the ztaskd server. If the server is not available (not responding to 'alive' requests
  within `ZTASKD_ALIVE_TIMEOUT` milliseconds), the function will be called directly, in-process.
  It is your responsibility to make sure that `func` won't block the worker process.
  
  For backwards compatibility, `.delay` will do the same thing as `.async`, but is deprecated.

- `func.after(seconds, *args, **kwargs)`

  This will cause the task to be sent to the `ztaskd` server, which will wait `seconds` 
  seconds to execute. If the server is not available, the requested delay is ignored and
  the function is called directly just like it's done for `func.async()`


Example
-------

    from django_ztask.decorators import task
    
    @task()
    def print_this(what_to_print):
        print what_to_print
        
    if __name__ == '__main__':
        
        # Call the function directly
        print_this('Hello world!')
        
        # Call the function asynchronously
        print_this.async('This will print to the ztaskd log')
        
        # Call the function asynchronously
        # after a 5 second delay
        print_this.after(5, 'This will print to the ztaskd log')
        

Implementing with Johnny Cache
==============================

Because [Johnny Cache](http://packages.python.org/johnny-cache/) monkey-patches all the Django query compilers, 
any changes to models in django-ztask that aren't properly patched won't reflect on your site until the cache 
is cleared. Since django-ztask doesn't concern itself with Middleware, you must put Johnny Cache's query cache
middleware in as a callable in the `ZTASKD_ON_LOAD` setting.

    ZTASKD_ON_LOAD = (
        'johnny.middleware.QueryCacheMiddleware',
        ...
    )

If you wanted to do this and other things, you could write your own function, and pass that in to 
`ZTASKD_ON_LOAD`, as in this example:

**myutilities.py**

    def ztaskd_startup_stuff():
        '''
        Stuff to run every time the ztaskd server 
        is started or reloaded
        '''
        from johnny import middleware
        middleware.QueryCacheMiddleware()
        ... # Other setup stuff

**settings.py**
    
    ZTASKD_ON_LOAD = (
        'myutilities.ztaskd_startup_stuff',
        ...
    )


TODOs and BUGS
==============
See: [http://github.com/odeoncg/django-ztask-odeon/issues](http://github.com/odeoncg/django-ztask-odeon/issues)
