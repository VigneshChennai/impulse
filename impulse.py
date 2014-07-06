#!/usr/bin/python

import sys
import paramiko
import traceback
import re
import threading
import select
import time
import signal


def signal_handler(s,f):
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class SSH:

    def __init__(self, host, username, password):
        
        self.host = host
        self.username = username
        self.password = password
        self.auto_input = True
        self.shell = "bash -s"
        self.__end__ = "--END-23464238676542-END--"
        self.__outbalance__ = ""
        self.status = "0"
        self.completion = threading.Event()
        self.inputs = Inputs(None)
        

    def __handle_input__(self):
        while self.alive:
            i, o, e = select.select( [sys.stdin], [], [], 1)
            if i:
                line = sys.stdin.readline().strip()
            else:
                continue
            if self.auto_input:
                print "[local] Manual entry received. Auto inputs will be disabled"
                self.auto_input = False
            if line.strip() == "__exit__":
                self.close()
                sys.exit(1)
            self.stdin.write(line+"\n")
            
    def __enter__(self):
        self.alive = True
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.host, username=self.username, 
                            password=self.password)
        self.client = client
        conn = self.client.get_transport().open_session()
        conn.set_combine_stderr(True)

        print "[local] Initializing shell"
        conn.exec_command(self.shell)
        self.stdin = conn.makefile("wb")
        self.stdout = conn.makefile("rb")
        self.conn = conn

        print "[local] Connected to host[%s]" % (self.host)
        print "[local] Starting step execution .. .."
        t = threading.Thread(target=self.__handle_input__)
        t.daemon = True
        t.start()
        t = threading.Thread(target=self.__read__)
        t.daemon = True
        t.start()

        return self
        
    def close(self):
        self.alive = False
        print "[local] Execution completed .. .."
        self.stdin.close()
        self.stdout.close()
        self.conn.close()
        self.client.close()
            
    def __exit__(self,  type, value, traceback):
        self.close()
        
    def __read__(self):
        while self.alive:
            while self.alive and not self.stdout.channel.recv_ready():
                time.sleep(0.3)
            data = self.stdout.channel.recv(10000)
            sys.stdout.write(data)
            sys.stdout.flush()
            if len(data) > 0:
                self.__analyze__(data)           
                
    def __analyze__(self, data):
        d = self.__outbalance__ + data
        status = False
        splitdata = d.split('\n')
        for line in splitdata:
            line = line.strip()
            if status:
                print "**** END ****"
                self.status = line
                self.completion.set()
                status = False
            elif line == self.__end__:
                status = True
            else:
                if self.inputs.cinput and self.auto_input:
                    answer = self.inputs.get_answer(line)
                    if answer:
                        self.stdin.write(answer)
                        self.stdin.flush()
                        
        self.__outbalance__ = splitdata[-1]
                    
    def __wait_for_completion__(self, timeout=None):
        self.completion.clear()
        if timeout:
            self.completion.wait(timeout)
            return self.completion.is_set()
        else:
            while True:
                self.completion.wait(1)
                if self.completion.is_set():
                    break

    def sudo(self, user, password):
        class Sudo:
            def __init__(self, ssh):
                self.ssh = ssh
            def __enter__(self):
                return self
            def __exit__(self,  type, value, traceback):
                self.ssh.stdin.write("exit\n")
        print "[local] Executin sudo"
        self.stdin.write("sudo -S -k -u '%s' bash -c "
                "\"echo;echo '%s';echo 0; bash\"\n" % (user, self.__end__))
        self.stdin.write(password+ "\n")
        if not self.__wait_for_completion__(5):
            raise RuntimeError("Executing sudo is not successful")
        return Sudo(self)
        
    def run(self, command, inputs=None, rets=True):
        self.inputs = Inputs(inputs)
        print "[local] Executing: %s" % command
        cmd = "%s;status=$?;echo;echo %s;echo $status;\n" %(
                    command,
                    self.__end__
                    )
        self.stdin.write(cmd)
        self.stdin.flush()
        self.__wait_for_completion__()
        print "[local] Command executed"
        if not self.status in ["0", ""]:
            raise RuntimeError("Command execution returned status <%s>" %(
                                str(self.status)
                                ))

    def get(self, remote, local):
        sftp = self.client.open_sftp()
        try:
            print "[local] Copying file from [%s]%s to [%s]%s" %(self.host, remote, "local", local)
            sftp.get(remote, local)
            print "[local] Copied successfully"
        except:
            error = traceback.format_exc()
            print error
            print "[local] Copy failed"    
        finally:
            try:
                sftp.close()
            except:
                pass

    def put(self, local, remote):
        sftp = self.client.open_sftp()
        try:
            print "[local] Copying file from [%s]%s to [%s]%s" %("local", local, self.host, remote)
            sftp.put(local, remote)
            print "[local] Copied successfully"
        except:
            error = traceback.format_exc()
            print error
            print "[local] Copy failed"    
        finally:
            try:
                sftp.close()
            except:
                pass

class Input:
    def __init__(self, question, answer, optional=False, atlast="\n"):
        self.question_pattern = re.compile(question)
        self.question = question
        self.answer = answer
        self.optional = False
        self.atlast = atlast
        self.next = None
    
    def next_input(self, question, answer, optional=False, atlast="\n"):
        self.next = Input(question, answer, optional,  atlast="\n")
        return self.next
    def next_inputs(inputs):
        self.next = inputs
        return inputs
    
class Inputs:
    def __init__(self, inputs):
        self.cinput = inputs

    def get_answer(self, question):
        cinput = self.cinput
        while True:
            if cinput and isinstance(cinput, Input):
                if cinput.question_pattern.match(question):
                    self.cinput = cinput.next
                    return cinput.answer + cinput.atlast
                elif self.cinput.optional:
                    cinput = input.next
                else:
                    return None
            elif cinput and type(cinput) == tuple:
                for i in cinput:
                    if i.question_pattern.match(question):
                        self.cinput = i.next
                        return cinput.answer + cinput.atlast
                return None
            else:
                return None


