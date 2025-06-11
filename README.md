Start of a collection of things I want running in cron. Mostly they'll make use of ntfy.sh to send me things. 

Using run.sh in cron just pass in the basename of the script you want to run.
I'll extend as required to run directories as well. Probably as <directory_name>/main.py 
so you just pass the directory as the parameter and run.sh
will sort out whether it's a file or a directory. That's easy
enough to do.

**rrklb-price**  
Uses yfinance to fetch the close price and change for Rocketlab (RKLB) and squirt it to my phone using ntfy.sh.  

Crontab entry  
```cron
0 8 * * 2-6 $HOME/cron_python/run.sh rklb-price
```


