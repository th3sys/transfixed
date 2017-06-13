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

Stage 2: Simple Orders
The following tests will be done with the client application logged on and session persistence feature turned off. For more information on session persistence tests see Stage 4.
Order Placement and Fill

1.  Place new DAY order BUY 1 <Futures 1> MKT.
2.  Receive Execution Report: ExecTransType=New, OrdStatus=New, ExecType=New.
3.  Receive Execution Report: ExecTransType=New, OrdStatus=Filled, ExecType=Fill.
4.  Confirm values of ClOrdID (11), OrderID (37), ExecID (17), and TransactTime (60).
Place and Cancel

1.  Place new DAY order BUY 5 <Call option 1> STP <P1 = price above the market>.
2.  Receive Execution Report: ExecTransType=New, OrdStatus=New, ExecType=New.
3.  Cancel order.
4.  Receive Execution Report: ExecTransType=New, OrdStatus=Pending Cancel, ExecType=Pending Cancel.
5.  Receive Execution Report: ExecTransType=New, OrdStatus=Canceled, ExecType=Canceled.
6.  Confirm values of ClOrdID (11), OrigClOrdID (41), OrderID (37), ExecID (17), StopPx (99), TransactTime (60).

