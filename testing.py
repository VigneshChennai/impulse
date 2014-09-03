import impulse
import time

with impulse.SSH('localhost', 'vignesh', 'borntowin') as conn:
    conn.run("ls")
    conn.run("echo Hello vignesh")
    with conn.sudo('root', 'borntowin'):
        conn.run("whoami")
        inputs  = impulse.Input(".*name.*", "Vigneshwaran P")
        conn.run("echo -n \"What's your name \";read n;echo \"Hi :-) $n\"",
                inputs)
