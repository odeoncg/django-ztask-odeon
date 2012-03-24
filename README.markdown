About
=====

django-ztask is a lightweight asynchronous task queue for Django based on zeromq.
It appeared as a [quick hack](http://www.zeromq.org/story:3) but proved to be a simple, solid and highly hackable alternative to [celery](http://celeryproject.org/).

This is a fork of of the [original project](https://github.com/dmgctrl/django-ztask) which seems unmaintained for almost an year.

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

    python manage.py ztaskd


Command-line arguments
----------------------

The `ztaskd` command takes a series of command-line arguments:

- `--noreload`
  
  By default, `ztaskd` will use the built-in Django reloader 
  to reload the server whenever a change is made to a python file. Passing
  in `--noreload` will prevent it from listening for changed files.
  (Good to use in production.)

- `-l` or `--loglevel`
  
  Choose from the standard `CRITICAL`, `ERROR`, `WARNING`, 
  `INFO`, `DEBUG`, or `NOTSET`. If this argument isn't passed 
  in, `INFO` is used by default.

- `-f` or `--logfile`
  
  The file to log messages to. By default, all messages are logged
  to `stdout`

- `--replayfailed`
  
  If a command has failed more times than allowed in the 
  `ZTASKD_RETRY_COUNT` (see below for more), the task is
  logged as failed. Passing in `--replayfailed` will cause all 
  failed tasks to be re-run.

- `--pidfile`

  The file to write the PID to. Required for stopping the daemon.

- `--stop`

  Stop the ztaskd instance indicated by `--pidfile`. The pidfile should be
  the same passed as an argument when the ztaskd server was started

Settings
--------

There are several settings that you can put in your `settings.py` file in 
your Django project. These are the settings and their defaults

    ZTASKD_URL = 'tcp://127.0.0.1:5555'

By default, `ztaskd` will run over TCP, listening on 127.0.0.1 port 5555. 

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

A recommended way to run in production would be to put something similar to 
the following in to your `rc.local` file. This example has been tested on 
Ubuntu 10.04 and Ubuntu 10.10:

    #!/bin/bash -e
    pushd /var/www/path/to/site
    sudo -u www-data python manage.py ztaskd --noreload -f /var/log/ztaskd.log --pidfile /var/run/ztask.pid &
    popd


Making functions in to tasks
============================

Decorators and function extensions make tasks able to run. 
Unlike some solutions, tasks can be in any file anywhere. 
When the file is imported, `ztaskd` will register the task for running.

**Important note: all functions and their arguments must be able to be pickled.**

([Read more about pickling here](http://docs.python.org/tutorial/inputoutput.html#the-pickle-module))

It is a recommended best practice that instead of passing a Django model object 
to a task, you intead pass along the model's ID or primary key, and re-get 
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

  Calling a function with `.async` will cause the function task to be called asyncronously 
  on the ztaskd server. For backwards compatability, `.delay` will do the same thing as `.async`, but is deprecated.

- `func.after(seconds, *args, **kwargs)`

  This will cause the task to be sent to the `ztaskd` server, which will wait `seconds` 
  seconds to execute.


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
