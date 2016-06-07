import logging, os, re, signal, time, threading, traceback, urllib2, httplib, socket, subprocess, random
from SocketServer import ThreadingMixIn
from BaseHTTPServer import HTTPServer
from mako.template import Template

def post(url, data='{}'):
    request = urllib2.Request(url, data)
    request.add_header('Content-Type', 'application/json; charset=utf-8')
    request.get_method = lambda: 'POST'
    return urllib2.urlopen(request)

def delete(url):
    request = urllib2.Request(url)
    request.get_method = lambda: 'DELETE'
    return urllib2.urlopen(request)

def rget(root, *args):
    node = root
    for arg in args:
        node = node.get(arg, {})
    return node
    
def mangle(key):
    return re.sub('[^a-zA-Z0-9]+', '_', re.sub('^[^a-zA-Z0-9]+', '', key))

def alive(pidfile):
    """
    Checks if a process identified is still running.
    @param  pidfile File containing the PID of the process to check for
    """
    try:
        with open(pidfile) as f:
            pid = f.read()
            os.kill(int(pid), 0)
    except (IOError, OSError):
        return False
    return True

def kill(pidfile, sig=signal.SIGKILL):
    """
    Signal a process
    @param  pidfile File containing PID of process to signal
    @param  sig     Signal to send, defalts to signal.SIGKILL
    """
    pid = None
    name = os.path.basename(pidfile)
    try:
        with open(pidfile) as f:
            pid = f.read()
            os.kill(int(pid), sig)

        logging.debug("Sent signal '%s' to '%s'", sig, name)
        return True
    except IOError:
        logging.debug("PID file '%s' doesn't exist", pidfile)
    except Exception, e:
        logging.warn("Failed to send signal '%s' to '%s' with PID %s: %s", sig, name, pid, str(e))
        logging.debug(traceback.format_exc())
    return False

def run(action, errormsg="Connection error: %s", graceperiod=0):
    """
    Run action() in background forever and retry with exponential backoff in case of errors.
    """
    starttime = time.time()

    def routine():
        timeout = 1.0
        while True:
            try:
                action()
                timeout = 1.0
            except Exception, e:
                # Don't warn for startup errors when graceperiod is set
                if starttime + graceperiod <= time.time():
                    logging.warn(errormsg, str(e))
                else:
                    logging.debug(errormsg, str(e))
                logging.debug(traceback.format_exc())
                
                # Introduce some randomness to avoid stampeding herds
                time.sleep(jitter(timeout))
                
                # Exponential backoff up to a maximum time
                timeout = min(timeout * 1.5, 15.0)
    
    thread = threading.Thread(target=routine)
    thread.daemon = True
    thread.start()

def shell(cmd):
    return subprocess.call(cmd, shell=True)

class UnixHTTPConnection(httplib.HTTPConnection):
    """
    Subclass of Python library HTTPConnection that uses a unix-domain socket.
    """
    def __init__(self, path):
        httplib.HTTPConnection.__init__(self, 'localhost')
        self.path = path
 
    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        self.sock = sock

class UnixHTTPServer(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_UNIX

    def get_request(self):
        # Client address is expected to be (ip, port) which is not what a unix socket returns
        request, client_address = HTTPServer.get_request(self)
        return request, ('127.0.0.1', '0')

def unixresponse(method, socketpath, url, body=None, headers={}):
    conn = UnixHTTPConnection(socketpath)
    conn.request(method, url, body, headers)
    return conn.getresponse()

def unixrequest(method, socketpath, url, body=None, headers={}):
    return unixresponse(method, socketpath, url, body, headers).read()

def renderTemplate(src, dst, vals):
    template = Template(filename=src)
    config = template.render(**vals)
    tmpfile = "%s.tmp" % dst
    with open(tmpfile, 'w') as f:
        f.write(config)

    # Rename tmpfile to avoid modifying an existing file in place which can
    # cause a process reading it concurrent to read inconsistent data
    os.rename(tmpfile, dst)

def jitter(duration):
    return duration * (0.75 + random.random() * 0.25)
