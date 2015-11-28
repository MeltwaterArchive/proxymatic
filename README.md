# Proxymatic
The proxymatic image forms one part of a network level service discovery solution. It dynamically configures proxies that forward network connections to the host where a service is currently running. By subscribing to events from discovery sources such as [Marathon](https://github.com/mesosphere/marathon) or [registrator](https://github.com/gliderlabs/registrator) the proxies can quickly be updated whenever a service is scaled or fails over.

## Environment Variables

 * **MARATHON_URL** - List of Marathon replicas, e.g. "http://marathon-01:8080/,http://marathon-02:8080/"
 * **MARATHON_CALLBACK_URL** - URL to register for Marathon HTTP callbacks, e.g. "http://\`hostname -f\`:5090/"
 * **REGISTRATOR_URL** - URL where registrator publishes services, e.g. "etcd://localhost:4001/services"
 * **REFRESH_INTERVAL=60** - Polling interval when using non-event capable backends. Defaults to 60 seconds.
 * **EXPOSE_HOST=false** - Expose services running in net=host mode. May cause port collisions when this container is also run in net=host mode. Defaults to false.
 * **HAPROXY=false** - Use HAproxy for TCP services instead of running everything through Pen. Defaults to false.
 * **VHOST_DOMAIN** - Enables nginx with virtual hosts for each service under this domain, e.g. "services.example.com"
 * **VHOST_PORT=80** - Port to serve virtual hosts from. Defaults to port 80.
 * **PROXY_PROTOCOL=false** - Enable proxy protocol on the nginx vhost which is needed when using the AWS ELB in TCP mode for websocket support.

## Command Line Usage

```
Usage: docker run meltwater/proxymatic:latest [options]...

Proxy for TCP/UDP services registered in Marathon and etcd

Options:
  -h, --help            show this help message and exit
  -m MARATHON, --marathon=MARATHON
                        List of Marathon replicas, e.g.
                        "http://marathon-01:8080/,http://marathon-02:8080/"
  -c CALLBACK, --marathon-callback=CALLBACK
                        URL to register for Marathon HTTP callbacks, e.g.
                        "http://`hostname -f`:5090/"
  -r REGISTRATOR, --registrator=REGISTRATOR
                        URL where registrator publishes services, e.g. "etcd
                        ://etcd-host:4001/services"
  -i INTERVAL, --refresh-interval=INTERVAL
                        Polling interval in seconds when using non-event
                        capable backends [default: 60]
  -e, --expose-host     Expose services running in net=host mode. May cause
                        port collisions when this container is also run in
                        net=host mode on the same machine [default: False]
  --pen-servers=PENSERVERS
                        Max number of backend servers for each pen service
                        [default: 32]
  --pen-clients=PENCLIENTS
                        Max number of pen client connections [default: 8192]
  --haproxy             Use HAproxy for TCP services instead of running
                        everything through Pen [default: False]
  --vhost-domain=VHOSTDOMAIN
                        Domain to add service virtual host under, e.g.
                        "services.example.com"
  --vhost-port=VHOSTPORT
                        Port to serve virtual hosts from [default: 80]"
  --proxy-protocol      Enable proxy protocol on the nginx vhost [default:
                        False]
  -v, --verbose         Increase logging verbosity
```

## Marathon

Given a Marathon URL, proxymatic will periodically fetch the running tasks and configure proxies that forward connections from the [servicePort](http://mesosphere.com/docs/getting-started/service-discovery/) to the host and port exposed by the task. If Marathon is started with [HTTP callback support](https://mesosphere.github.io/marathon/docs/event-bus.html) then proxymatic can be notified immediately, which cuts the response time in case of failover or scaling.

```
docker run --net=host \
  -e MARATHON_URL=http://marathon-host:8080 \
  -e MARATHON_CALLBACK_URL=http://$(hostname --fqdn):5090 \
  meltwater/proxymatic:latest
```

Given the service below, proxymatic will listen on port 1234 and forward connections to port 8080 inside the container. 

```
{
  "id": "/myproduct/mysubsystem/myservice",
  "container": {
    "type": "DOCKER",
    "docker": {
      "image": "registry.example.com/myservice:1.0.0",
      "network": "BRIDGE",
      "portMappings": [
        { "containerPort": 8080, "servicePort": 1234 }
      ]
    }
  },
  "instances": 2
}
```

### Rolling Upgrades/Restarts

There are a number of things that need to be in place for the orchestration of graceful rolling upgrades. Proxymatic will remove tasks that fail their health check immediately. This can be used to implement rolling upgrades/restarts without any failing requests.

* Adjust Mesos slave parameters to gracefully stop tasks. Default behavior is to use `docker kill` which will just send a SIGKILL and terminate the task immediately. Setting the *--docker_stop_timeout* flag will ensure Mesos slaves uses the `docker stop` command. Start the Mesos slave with e.g.

```
  --executor_shutdown_grace_period=90secs --docker_stop_timeout=60secs
```

* Add an Marathon app health check that is fast enough to run within the stop timeout, and with plenty room to finish requests. For example

```
  "healthChecks": [
    {
      "protocol": "HTTP",
      "path": "/health",
      "portIndex": 0,
      "gracePeriodSeconds": 60,
      "intervalSeconds": 20,
      "timeoutSeconds": 10,
      "maxConsecutiveFailures": 3
    }
  ]
```

* Trap SIGTERM in your app and start failing the health check with e.g. *HTTP 503 Service Unavailable*. The  implementation of this will vary greatly between apps and languages. This example uses [Python Flask](http://flask.pocoo.org/)

```
import signal
from flask import Flask

app = Flask(__name__)
healty = True

# Start failing the health check when receiving SIGTERM
def sigterm_handler(_signo, _stack_frame):
  global healty
  healty = False
signal.signal(signal.SIGTERM, sigterm_handler)

@app.route('/health')
def health():
  if healty:
    return 'OK'
  return 'Stopping', 503
```

## Virtual Hosts

The --vhost-domain and $VHOST_DOMAIN parameter can be used to automatically configure an nginx with virtual hosts for each service. This is similar to the [Deis router](http://docs.deis.io/en/latest/understanding_deis/components/#router) component. To use this feature start proxymatic like

```
docker run -p 80:80 -e VHOST_DOMAIN=app.example.com
```

And create a wildcard DNS record that points *.app.example.com to the IP of the 
container host. Each service will automatically get a vhost under the app.example.com setup in nginx. For example

| Virtual Host URL   | Marathon Id | Registrator SERVICE_NAME |
| :----------------- | :---------- | :----------------------- |
| http://myservice.app.example.com | myservice | myservice |
| http://service.system.product.app.example.com | /product/system/service | service.system.product |

## Deployment

### Systemd and CoreOS/Fleet

Create a [Systemd unit](http://www.freedesktop.org/software/systemd/man/systemd.unit.html) file in **/etc/systemd/system/proxymatic.service** with contents like below. Using CoreOS and [Fleet](https://coreos.com/docs/launching-containers/launching/fleet-unit-files/) then add the X-Fleet section to schedule the unit on all cluster nodes.

```
[Unit]
Description=Proxymatic dynamic service gateway
After=docker.service
Requires=docker.service

[Install]
WantedBy=multi-user.target

[Service]
Environment=IMAGE=meltwater/proxymatic:latest NAME=proxymatic

# Allow docker pull to take some time
TimeoutStartSec=600

# Restart on failures
KillMode=none
Restart=always
RestartSec=15

ExecStartPre=-/usr/bin/docker kill $NAME
ExecStartPre=-/usr/bin/docker rm $NAME
ExecStartPre=-/bin/sh -c 'if ! docker images | tr -s " " : | grep "^${IMAGE}:"; then docker pull "${IMAGE}"; fi'
ExecStart=/usr/bin/docker run --net=host \
    --name=${NAME} \
    -e MARATHON_URL=http://marathon-host:8080 \
    -e MARATHON_CALLBACK_URL=http://%H:5090 \
    $IMAGE

ExecStop=/usr/bin/docker stop $NAME

[X-Fleet]
Global=true
```

### Puppet Hiera

Using the [garethr-docker](https://github.com/garethr/garethr-docker) module

```
classes:
  - docker::run_instance

docker::run_instance:
  'proxymatic':
    image: 'meltwater/proxymatic:latest'
    net: 'host'
    env:
      - "MARATHON_URL=http://marathon-host:8080"
      - "MARATHON_CALLBACK_URL=http://%{::hostname}:5090"
```
