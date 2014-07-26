import impulse
import time

with impulse.SSH('localhost', 'vignesh', 'borntowin') as conn:
    conn.run("ls")
    conn.run("echo Hello vignesh")
    
