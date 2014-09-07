#!/usr/bin/python

import sys
import paramiko
import traceback
import re
import threading
import select
import time
import signal
import Queue
import copy
import random

#Handler for keyboard interrupt signal
#upon recieving the keyboard interrupt signal,
#module will exits the scripts. 
def signal_handler(s,f):
    sys.exit(0)

#Initialize the Interrupt signal handling
signal.signal(signal.SIGINT, signal_handler)

#SSH is the main class which to used to connect to remote servers, 
#run commands and process inputs running the remote server.
class SSH:

    #This method initializes all the attributes required to connect
    #and execute commands in the remote server
    def __init__(self, host, username, password, port=22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.shell = "bash -s"        
        
    #This method connects to remote server based on the details 
    #initialized by the  __init__ method
    def __enter__(self):
        self.alive = True
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.host, username=self.username, 
                            password=self.password, port=self.port)
        self.client = client
        conn = self.client.get_transport().open_session()
        #initializing pty mode by default
        conn.get_pty()
        print "[local] Initializing shell"
        conn.exec_command(self.shell)
        self.stdin = conn.makefile("wb")
        self.stdout = conn.makefile("rb")
        self.conn = conn

        print "[local] Connected to host[%s]" % (self.host)
        print "[local] Template execution started"

        #Creating a new daemon thread to process output from 
        #command executed in the remote server
        t = threading.Thread(target=self.__read__)
        t.daemon = True
        t.start()
        self.cem = CommandExecutionAndMonitoring(self.host)
        
        def __input__(data):
            self.stdin.write(data)
            self.stdin.flush()
        
        def __output__(data):
            sys.stdout.write(data)
            sys.stdout.flush()
        self.cem.add_input_listener(__input__)
        self.cem.add_output_listener(__output__)
        
        return self

    #close method is used to close all the connections to the remote server on 
    #at the end of execution    
    def close(self):
        self.alive = False
        print "[local] Template execution completed"
        self.stdin.close()
        self.stdout.close()
        self.conn.close()
        self.client.close()
            
    def __exit__(self,  type, value, traceback):
        self.close()
    
    #__read__ method is used to read the output data from command 
    #executed in remote server asynchronously   
    def __read__(self):
        while self.alive:
            while self.alive and not self.stdout.channel.recv_ready():
                time.sleep(0.3)
            data = self.stdout.channel.recv(10000)
            self.cem.analyze(data)

    def sudo(self, user, password):
        return self.cem.sudo(user, password)
    
    #This method runs the command and check it's 
    #exit status whether is completed successfully.
    def run(self, command, inputs=None, rets=True):
        return self.cem.run(command, inputs)

    #get method is used to get a remote file to the local system
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

    #put method is used to put a file on remote server from local system
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


#Input class is used to store question and corresponding answer
#which need to be provide to the command during execution.
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

#Inputs class is used by SSH class to get the answer for questions
#asked by command during its execution
class Inputs:
    def __init__(self, inputs):
        self.cinput = inputs
    
    #Question(actually every line of output) asked by the command is passed to 
    #this method.
    #This method will return answer if it founds else returns None
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
                
class Buffer:
    
    def __init__(self):
        self.buffer_entry = Queue.Queue()
        self.current_entry = BufferEntry()
        self.lock = threading.Lock()
    
    def add_character(self, character):
        with self.lock:
            if character == '\n':
                self.buffer_entry.put(self.current_entry)
                self.current_entry = BufferEntry()
            else:
                self.current_entry.add_character(character)
    
    def get_entry(self):
        try:
            return self.buffer_entry.get(False)
        except:
            with self.lock:
                local_copy = copy.deepcopy(self.current_entry)
            return local_copy
    
    def clear():
        with self.buffer_entry.mutex:
            self.buffer_enty.queue.clear()
        with lock:
            self.current_entry = BufferEntry()
    
class BufferEntry:
    
    def __init__(self):
        self.line = ""
        self.processed = False
        self.answered = False
    
    def is_processed(self):
        return processed
        
    def set_processed(self, processed = True):
        self.processed = processed

    def is_answered(self):
        return self.answered
    
    def set_answered(self, answered = True):
        self.answered = answered
        
    def get_line(self):
        return self.line
    
    def add_character(self, character):
        self.line += character

class CommandExecutionAndMonitoring:
    def __init__(self, host):
        self.host = host
        self.auto_input = True
        self.__begin__ = "@--BEGIN-%s--@" % (random.random())
        self.__end__ = "@--END-%s-END--@" % (random.random())
        self.status = "notrunning"
        self.exit_code = ""
        self.completion = threading.Event()
        self.__print_buffer__ = ""
        self.buffer = Buffer()
        self.inputs = Inputs(None)
        
        t = threading.Thread(target=self.__user_inputs_analyzer__)
        t.daemon = True
        t.start()
        
        self.input_listeners = []
        self.output_listeners = []
        
    def run(self, command, inputs, wait = True):
        if self.status != "completed" and self.status != "notrunning":
            raise Exception("Cannot execute a command while "\
                            "another command is running")
        self.status = "ready"
        self.inputs = Inputs(inputs)
        self.auto_input = True
        
        cmd = "echo;echo %s; %s;status=$?;echo \"%s$status\"\n" %(
                    self.__begin__,
                    command,
                    self.__end__
                    )
        print "\n[local] Executing %s" % (command)
        self.__input__(cmd)
        if wait:
            self.__wait_for_completion__()
            print "\r               "
            print "[local] Command executed"
            if not self.exit_code in ["0", ""]:
                raise RuntimeError("Command execution returned status <%s>" %(
                                    str(self.exit_code)
                                    ))
            return self.exit_code
        
    def sudo(self, user, password):
        class Sudo:
            def __init__(self, cem):
                self.cem = cem
            def __enter__(self):
                self.cem.status = "ready"
                self.cem.auto_input = True
                self.cem.inputs = Inputs(Input(".*assword",password))
                self.cem.__input__("echo;echo %s;sudo -S -k -u '%s' -i "
                                "bash -c \"echo;echo '%s'0;bash --login\"\n" 
                                %(self.cem.__begin__,user,self.cem.__end__))
                if not self.cem.__wait_for_completion__(5):
                    raise RuntimeError("Executing sudo is not successful")
                print "\r[Local] sudo successfull"
                return self
            def __exit__(self,  type, value, traceback):
                self.cem.__input__("exit\n")
                print "[Local] sudo command completed"
        print "[local] Executing sudo"
        
        return Sudo(self)
        
    def analyze(self, data):
        out = []
        ans = []
        for c in data:
            if self.status == "running":
                answer = self.__input_analyzer__(c)
                if answer:
                    ans.append(answer)
            o = self.__print_analyzer__(c)
            if o:
                if o == '\n':
                    o = '\n[%s] ' % (self.host)
                out.append(o)
        if len(out) > 0:
            self.__output__("".join(out))
            
        if len(ans) > 0:    
            for a in ans:
                self.__input__(a)

    def add_output_listener(self, listener):
        self.output_listeners.append(listener)
        
    def add_input_listener(self, listener):
        self.input_listeners.append(listener)
        
    def __output__(self, data):
        for listener in self.output_listeners:
            listener(data)
        
    def __input__(self, data):
        for listener in self.input_listeners:
            listener(data)
        
    def __answers__(self, data):
        self.__input__(data)
        
    def __command_status__(self, status):
        if status == "completed":
            self.completion.set()
        self.status = status

    
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
                
    def __input_analyzer__(self, character):
            self.buffer.add_character(character)
            entry = self.buffer.get_entry()
            if not entry.is_answered():
                if self.inputs.cinput and self.auto_input:
                    answer = self.inputs.get_answer(entry.get_line())
                    if answer:
                        return answer
    
    def __print_analyzer__(self, character):
        pbuffer = self.__print_buffer__

        if self.status == "ready":
            #This section of code analyse whether any command is started executing.
            #if it founds any, then it will call the __command_running__() function
            
            if ('\n' + self.__begin__).startswith(pbuffer + character):
                if len(pbuffer + character) == len(self.__begin__) + 1:
                    self.__print_buffer__ = ""
                    self.__command_status__("running")
                else:
                    self.__print_buffer__ += character
            else:
                if ('\n' + self.__begin__).startswith(character):
                    self.__print_buffer__ = character
                else:
                    self.__print_buffer__ = ""
        elif self.status == "running":
            #This section of code analyse whether any command has finished execution.
            #if it founds any, the it will call the __command_completed__()
            if self.__end__.startswith(pbuffer + character):
                if len(pbuffer + character) == len(self.__end__):
                    self.__print_buffer__ = ""
                    self.__command_status__("reaping")
                    return
                else:
                    self.__print_buffer__ += character
            else:
                if self.__end__.startswith(character):
                    self.__print_buffer__ = character
                else:
                    self.__print_buffer__ = ""
                return pbuffer + character
        elif self.status == "reaping":
            if character == '\n' or character == '\r':
                self.exit_code = self.__print_buffer__
                self.__command_status__("completed")
            else:
                self.__print_buffer__ += character

    def __user_inputs_analyzer__(self):
        while True:
            i, o, e = select.select( [sys.stdin], [], [], 1)
            if i:
                line = sys.stdin.readline().strip()
            else:
                continue
            #If any manual input received from the user, 
            #the below code will disable the
            #further automatic input from the script for the current command
            if self.auto_input:
                print "[local] Manual entry received." \
                        " Auto inputs will be disabled" \
                        " for the current running command"
                self.auto_input = False

            self.__answers__(line + "\n")
    

        

