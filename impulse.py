#!/usr/bin/python

import sys
import paramiko
import traceback
import re
import threading
import select
import time
import signal

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
        self.auto_input = True
        self.shell = "bash -s"
        self.__begin__ = "%--BEGIN-23464238676542-BEGIN--%"
        self.__end__ = "%--END-23464238676542-END--%"
        self.__outbalance__ = ""
        self.status = ""
        self.completion = threading.Event()
        self.inputs = Inputs(None)
        
        self.print_buffer = ""
        
        self.command_running = False
        self.command_status = "notstarted"
        
        self.last_line_answered = False
        
    #This method is executed when a new command started executing
    def __command_running__(self):
        self.command_running = True
        self.command_status = "running"
    
    #This method is executed when a commands exits/terminates
    def __command_completed__(self):
        self.command_running = False
        self.command_status = "completed"
    
    #Prints the output of the command after analysing
    def __print__(self, content):
        pbuffer = []
        sbuffer = ""
        for c in content:
            #sending each character of command output to 
            #__print_analyser__ for analysing whether it needs to be
            #printed to screen or not.
            #
            #It return None if nothing need to printed
            #else returns the characters need to printed.
            d = self.__print_analyser__(c)
            if d:
                pbuffer.append(d)
        
        #printing the content if the pbuffer has content
        if len(pbuffer) > 0:
            sys.stdout.write("".join(pbuffer))
            sys.stdout.flush()
            

    #This method used to check whether to print command output to screen or not
    #It does it by analysing the output from remote server and identifies if a command
    #starts or exits
    #
    #It will return contents only when the command is running
    #else None will be returned
    def __print_analyser__(self, content):
        pbuffer = self.print_buffer
        #sys.stdout.write(content)
        #sys.stdout.flush()
        if not self.command_running:
            #This section of code analyse whether any command is started executing.
            #if it founds any, then it will call the __command_running__() function
            if ('\n' + self.__begin__).startswith(pbuffer + content):
                if len(pbuffer + content) == len(self.__begin__) + 1:
                    self.print_buffer = ""
                    self.__command_running__()
                else:
                    self.print_buffer += content
            else:
                if ('\n' + self.__begin__).startswith(content):
                    self.print_buffer = content
                else:
                    self.print_buffer = ""
        else:
            #This section of code analyse whether any command has finished execution.
            #if it founds any, the it will call the __command_completed__()
            if self.__end__.startswith(pbuffer + content):
                if len(pbuffer + content) == len(self.__end__):
                    self.print_buffer = ""
                    self.__command_completed__()
                    return
                else:
                    self.print_buffer += content
            else:
                if self.__end__.startswith(content):
                    self.print_buffer = content
                else:
                    self.print_buffer = ""
                return pbuffer + content
    
    #__handle_input__ method is used to check for inputs provided by user from the console.
    #Instead of blocking IO, it uses 'select' to perform asynchronous IO on the console input.       
    def __handle_input__(self):
        while self.alive:
            i, o, e = select.select( [sys.stdin], [], [], 1)
            if i:
                line = sys.stdin.readline().strip()
            else:
                continue
            #If any manual input received from the user, the below code will disable the
            #further automatic input from the script
            if self.auto_input:
                print "[local] Manual entry received." \
                        " Auto inputs will be disabled" \
                        " for the current running command"
                self.auto_input = False
            #Typing "__exit__" in the console will kill the script execution and terminated the 
            #script
            if line.strip() == "__exit__":
                self.close()
                sys.exit(1)
            self.stdin.write(line+"\n")
    
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

        #Creating a new daemon thread to handle inputs for user
        t = threading.Thread(target=self.__handle_input__)
        t.daemon = True
        t.start()
        
        #Creating a new daemon thread to process output from 
        #command executed in the remote server
        t = threading.Thread(target=self.__read__)
        t.daemon = True
        t.start()
        #disable the echo in pty mode
        #self.__run__("stty -echo")
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
            self.__print__(data)
            if len(data) > 0:
                self.__analyze__(data)           
    
    #__analyze__ method is responsible for checking the end of command execution
    #and trigger completed signal
    #
    #It is also responsible for automatica input mechanism            
    def __analyze__(self, data):
        d = self.__outbalance__ + data
        status = False
        splitdata = d.split('\n')
        if self.last_line_answered:
            if len(splitdata) > 1:
                self.last_line_answered = False
                del splitdata[0]
            else:
                return
        last_answered_line = 0
        count = 0
        #analysing each row
        for line in splitdata:
            count += 1
            line = line.strip()
            if status:
                self.status = line
                #emitting completion signal
                self.completion.set()
                status = False
            elif line == self.__end__:
                status = True
            else:
                if self.inputs.cinput and self.auto_input:
                    answer = self.inputs.get_answer(line)
                    if answer:
                        last_answered_line = count
                        self.stdin.write(answer)
                        self.stdin.flush()
        #Analysing whether last line answer or not
        if len(splitdata) == last_answered_line:
            self.last_line_answered = True
        else:
            self.last_line_answered = False
            self.__outbalance__ = splitdata[-1]
    
    #This method block the thread which call this method 
    #until it receives a command completion signal
    #
    #It also supports timer
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
    
    #Switching the user using sudoo
    #Sudo command should not be used with run method.
    #Required sudo functionality can be achieved by calling this method
    def sudo(self, user, password):
        class Sudo:
            def __init__(self, ssh):
                self.ssh = ssh
            def __enter__(self):
                return self
            def __exit__(self,  type, value, traceback):
                self.ssh.stdin.write("exit\n")
        print "[local] Executing sudo"
        self.inputs = Inputs(Input(".*assword",password))
        self.stdin.write("echo;echo %s;sudo -S -k -u '%s' -i "
                        "bash -c \"echo;echo '%s';echo 0;bash --login\"\n" 
                        %(self.__begin__,user,self.__end__))
        if not self.__wait_for_completion__(5):
            raise RuntimeError("Executing sudo is not successful")
        return Sudo(self)
    
    #__run__ is method which actually invokes the command in the remote server
    def __run__(self, command, inputs=None, rets=True):
        self.auto_input = True
        self.inputs = Inputs(inputs)
        cmd = "echo;echo %s; %s;status=$?;echo;echo %s;echo \"$status\";echo\n" %(
                    self.__begin__,
                    command,
                    self.__end__
                    )
        self.stdin.write(cmd)
        self.stdin.flush()
        self.__wait_for_completion__()

    #This method runs the command and check it's 
    #exit status whether is completed successfully.
    def run(self, command, inputs=None, rets=True):
        print "[local] Executing: %s" % command
        #self.commandStatus = CommandStatus(command)
        #self.commandStatus.running()
        self.__run__(command, inputs, rets)
        print "[local] Command executed"
        if not self.status in ["0", ""]:
            raise RuntimeError("Command execution returned status <%s>" %(
                                str(self.status)
                                ))

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

#Instance of CommandStatus class is used to store the 
#current status in command execution in SSH class
class CommandStatus:
    def __init__(command):
        self.command = command
        self.running = False
        
    def isRunning():
        return self.running
    def running():
        self.running = True

#Input calss is used to store question and corresponding answer
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



