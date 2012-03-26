#!/bin/sh

# you need to create the directories for PIDFILE and LOGFILE and give them the necessary permissions
PIDFILE="/var/run/ztask/ztask.pid"
LOGFILE="/var/log/ztask/ztask.log"
WORKDIR=`dirname "$0"`
cd "$WORKDIR"

cp_start()
{
 ./manage.py ztaskd --logfile "$LOGFILE" --pidfile "$PIDFILE" --noreload --daemonize
}

cp_stop()
{
 ./manage.py ztaskd --pidfile "$PIDFILE" --stop
}

cp_restart()
{
 cp_stop >/dev/null
 cp_start
}

case "$1" in
 "start")
  cp_start
 ;;
 "stop")
  cp_stop
 ;;
 "restart")
  cp_restart
 ;;
 *)
  "$@"
 ;;
esac

