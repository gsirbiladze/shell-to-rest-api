#!/usr/bin/env python

##########################################################################
#
#   Name: Shell to REST API
__version__ = '1.5'
__author__  = 'Grigol Sirbiladze'
#   E-mail: grigoli@gmail.com
#   Date: 10/2019
#   License: MIT
#
##########################################################################


import json
import subprocess
import signal

from time      import sleep
from datetime  import datetime
from textwrap  import dedent
from threading import Thread
from sys       import exit, version_info, argv
from os.path   import dirname, splitext, basename, join
from argparse  import ArgumentParser, RawTextHelpFormatter

if version_info[0] < 3:
    from SocketServer import ThreadingMixIn
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
else:
    from socketserver import ThreadingMixIn
    from http.server import HTTPServer, BaseHTTPRequestHandler


def dprint(string):
    """ Just print string with datetime """
    print("%s:> %s" % (datetime.now().strftime('%Y-%m-%d %H:%M:%S%Z'), string) )


class MThreadHTTPServer(HTTPServer, ThreadingMixIn):
    """Threaded HTTP Server"""


class ShellToWebHandler(BaseHTTPRequestHandler):
    
    def __init__(self, request, client_address, server):
        BaseHTTPRequestHandler.__init__(self, request, client_address, server)
        # Since GET gets initialized after we won't have "cmd_status_store" instantiate here
        # I has to be done from outside
        self.cmd_status_store = {}


    @staticmethod
    def jresponse(data):
        """ Returns JSON tructured string """
        return json.dumps(data) if type(data) is dict else json.dumps({"data" : str(data)})


    def response_header(self, response=200, complete_response=True, headers={}):
            """ Response Header Assembler 
                -------------------------

                response: HTTP response code (Default: 200)
                headers: dictianry of headers {"Key1":"Value1", "Key2":"Value2", ...} (Default: Empty)
                complete_response: Finalize header response True/False (Default: True)
            """
            self.send_response(response)    
            self.send_header('Content-Type', 'application/json')
            # self.send_header('Python-Verion-Info', str(version_info))

            if type(headers) is dict:
                for hk, hv in headers.items(): self.send_header(hk, str(hv))

            if complete_response: self.end_headers()


    def do_GET(self):
        """ """        
        if not hasattr(self, 'cmd_status_store') or self.path not in self.cmd_status_store.keys():
            # dprint("cmd_status_store: %s" % self.cmd_status_store)
            response_content =  self.jresponse({
                "name" : "Shell to REST API",
                "version": __version__,
                "commands_list" : list(self.cmd_status_store.keys())
                })
        else:
            response_content =  self.jresponse(self.cmd_status_store[self.path].get('status', {}))

        self.response_header()
        self.wfile.write(response_content.encode())


class SafeShellToWebServer(object):
    """ SafeShellToWebServer """

    def __init__(self, configuration, server_address='', port=8989):
        if not configuration or type(configuration) is not dict:
            raise(Exception("Shell commands are missing (Invalid parameter 'configuration=%s')" % (str(configuration))))

        self.config_and_status   = configuration
        self.web_2_shell_handler = ShellToWebHandler
        self.web_2_shell_server  = MThreadHTTPServer((server_address, port), self.web_2_shell_handler)
        self.web_2_shell_handler.cmd_status_store = self.config_and_status

        self._thread_list = set()
        self._running = True


    def execute_command(self, timeout, command, *arguments):
        """ Execute shell command """

        def pwait(ep, seconds=5):
            steps  = 0
            max_step = seconds * 5
            while ep.poll() is None and steps<max_step and self._running:
                sleep(0.2)
                steps+=1

            if ep.poll() is None:
                ep.kill()
                cmdln = ' '.join(ep.args)
                raise(Exception('%s\nCOMMAND TIMEOUT' % (cmdln)))

            return  ep.communicate()

        exec_command, out, err = [], b'',b''
        exec_command.append(command)
        if len(arguments)>0: exec_command.extend(arguments)

        try:
            ep = subprocess.Popen(exec_command, bufsize=0, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            out, err = pwait(ep, timeout)
        except Exception as e:
            err = bytes(str(e).encode('utf8'))
        finally:
            return (out.decode('utf8'), err.decode('utf8'))


    def _command_dedicated_process(self, cmdpath):
        """ Run all commands and propagate status """
        cmd = self.config_and_status[cmdpath]
        
        # Timeout can be overwritten by setting up overwrite_timeout
        # If command wants more than 60 seconds
        timeout   = cmd.get('timeout', 5)  if cmd.get('timeout', 5) < 60 else cmd.get('overwrite_timeout', 60) 
        interval  = cmd.get('interval', 5)
        command   = cmd.get('command')
        arguments = cmd.get('arguments', [])
        # Make sure all are string
        arguments = [ str(a) for a in arguments]

        def wait(seconds=5):
            steps = 0
            max_step = seconds*5
            while steps<max_step and self._running:
                sleep(0.2)
                steps+=1

        dprint("Starting executing '%s(%s)', timeout: %s,  interval: %s" % (cmdpath, command, timeout, interval))
        while self._running:
            (out, err) = self.execute_command(timeout, command, *arguments)

            jout = None
            jerr = None

            try:
                jout = json.loads(out)
            except:
                out = out.split('\n')

            try:
                jerr = json.loads(err)
            except:
                err = err.split('\n')

            cmd['status'] = { 'message' : jout if jout else out, 'error' : jerr if jerr else err}

            if interval >= 0:
                wait(interval)
            else:
                break

        dprint("End executing '%s(%s)' " % (cmdpath, command))


    def _start_command_threads(self):
        """ Run each command in a dedicated thread """
        for cmdpath in self.config_and_status.keys():
            thrd = Thread(target=self._command_dedicated_process, args=(cmdpath,), name=cmdpath)
            self._thread_list.add(thrd)
            thrd.start()


    @property
    def thread_list(self):
        return set([ tl.name for tl in self._thread_list ])


    def _count_live_threads(self):
        """ Clear stack from stopped threads and return live count"""
        stopped_threads = [ thrd for thrd in self._thread_list if not thrd.is_alive() ]
        for thrd in stopped_threads: self._thread_list.remove(thrd)
        
        # Return live threads count
        return len(self._thread_list)


    def _signal_handler(self, signum, frame):
        """ Signals process stopper """
        dprint('Shutting down server ...')
        self._running = False
        if hasattr(self.web_2_shell_server, 'socket'):
            self.web_2_shell_server.socket.close()
            self.web_2_shell_server.shutdown()

        while self._count_live_threads() > 0: sleep(0.01)


    def _register_signals(self):
        """ Start listening to OS signals """
        signal.signal(signal.SIGINT,  self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)


    def run_server(self):
        """ Run Server """
        try:
            self._register_signals()
            self._start_command_threads()
            Thread(target=self.web_2_shell_server.serve_forever).start()
            dprint("HTTP Server is listening on '%s:%s' ..." % (self.web_2_shell_server.server_address))
        except Exception as e:
            dprint("Unable to start HTTP Server ...\n ---> %s\n ---> Exiting"%e)
            exit(1)
        
        while self._running: sleep(0.2)


def get_cli_parameters():
    parser = ArgumentParser(usage="%(prog)s", formatter_class=RawTextHelpFormatter)

    parser.add_argument("-a", "--server-address", default="0.0.0.0", help="Server address (default: %(default)s)")
    parser.add_argument("-p", "--port",   default=8989, type=int, help="Server port (default: %(default)s)")
    parser.add_argument("-c", "--config", default="file://%s.json" % join(dirname(argv[0]), splitext(basename(argv[0]))[0]),
            help=dedent("""\
                                JSON format String or configuration file (default: %(default)s)
                                Configuration format example:
                                        { 
                                            "/path1" : {
                                                "interval": (default: 5), # If it's set to less than 0, command will be executed only once
                                                "timeout":  (default: 5), # Not more than 1 minute (60 seconds)
                                                "command" : "cmd",
                                                "arguments" : ["arg1", "arg2", "arg3", ...]
                                            },
                                            "/path2" : {
                                                "command" : "cmd",
                                                "arguments" : ["arg1", "arg2", "arg3", ...]
                                            }
                                        }
                                """)
       )

    return parser


if __name__ == '__main__':

    parser = get_cli_parameters()
    arguments = parser.parse_args() 

    try:
        if arguments.config[:7] == 'file://':
            with open(arguments.config[7:]) as config: configuration = json.load(config)    
        else:
            configuration = json.loads(arguments.config)

        SafeShellToWebServer(configuration=configuration, server_address=arguments.server_address, port=arguments.port).run_server()
    except Exception as e:
        dprint(e)
        parser.print_help()

