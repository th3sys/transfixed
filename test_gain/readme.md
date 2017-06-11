http://help.cqg.com/continuum/#!Documents/fixconnectconformancetest.htm

Stage 1: Log On and Log Off
Successful Log On, Clock, and Heartbeats

1.  Successfully open TCP socket connection.
2.  Send a Logon message with proper trader login and password.
3.  Receive Logon confirmation message.
4.  Wait for 2-3 heartbeat time intervals, check that sides exchange with Heartbeat messages.*
5.  Check that SendingTime values in Heartbeat messages are close on FIX client and CQG side.
6.  Send a Logout message.
7.  Close the TCP socket connection.

