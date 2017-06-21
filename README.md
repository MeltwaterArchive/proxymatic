# Proxymatic
[![Travis CI](https://img.shields.io/travis/meltwater/proxymatic/master.svg)](https://travis-ci.org/meltwater/proxymatic)
[![Coverage Status](https://codecov.io/github/meltwater/proxymatic/coverage.svg?branch=master)](https://codecov.io/github/meltwater/proxymatic?branch=master&view=all)

The proxymatic image forms one part of a network level service discovery solution. It dynamically configures proxies that forward network connections to the host where a service is currently running. By subscribing to events from discovery sources such as [Marathon](https://github.com/mesosphere/marathon) or [registrator](https://github.com/gliderlabs/registrator) the proxies can quickly be updated whenever a service is scaled or fails over.

## Environment Variables

 * **MARATHON_URL** - List of Marathon replicas, e.g. "http://marathon-01:8080/,http://marathon-02:8080/"
 * **REGISTRATOR_URL** - URL where registrator publishes services, e.g. "etcd://localhost:4001/services"
 * **STATUS_ENDPOINT=0.0.0.0:9090** - Expose /status endpoint and HAproxy stats on this ip:port
 * **REFRESH_INTERVAL=60** - Polling interval when using non-event capable backends. Defaults to 60 seconds.
 * **EXPOSE_HOST=false** - Expose services running in net=host mode. May cause port collisions when this container is also run in net=host mode. Defaults to false.
 * **HAPROXY=true** - Use HAproxy for TCP services instead of running everything through Pen. Defaults to true.
 * **VHOST_DOMAIN** - Enables nginx with virtual hosts for each service under this domain, e.g. "services.example.com"
 * **VHOST_PORT=80** - Port to serve virtual hosts from. Defaults to port 80.
 * **PROXY_PROTOCOL=false** - Enable proxy protocol on the nginx vhost which is needed when using the AWS ELB in TCP mode for websocket support.
 * **GROUP_SIZE=1** - Number of Proxymatic instances serving this cluster. Per container connection limits are divided by this number to ensure a globally coordinated maxconn per container.

## Command Line Usage

```
Usage: docker run meltwater/proxymatic:latest [options]...

Proxy for TCP/UDP services registered in Marathon and etcd

Options:
  -h, --help            show this help message and exit
  -m MARATHON, --marathon=MARATHON
                        List of Marathon replicas, e.g.
                        "http://marathon-01:8080/,http://marathon-02:8080/"
  -r REGISTRATOR, --registrator=REGISTRATOR
                        URL where registrator publishes services, e.g. "etcd
                        ://etcd-host:4001/services"
  -i INTERVAL, --refresh-interval=INTERVAL
                        Polling interval in seconds when using non-event
                        capable backends [default: 60]
  -e, --expose-host     Expose services running in net=host mode [default:
                        False]
  --status-endpoint=STATUSENDPOINT
                        Expose /status endpoint and HAproxy stats on this
                        ip:port [default: 0.0.0.0:9090]. Specify an empty
                        string to disable this endpoint
  --group-size=GROUPSIZE
                        Number of Proxymatic instances serving this cluster.
                        Per container connection limits are divided by this
                        number to ensure a globally coordinated maxconn per
                        container [default: 1]
  --max-connections=MAXCONNECTIONS
                        Max number of connection per service [default: 8192]
  --pen-servers=PENSERVERS
                        Max number of backends for each service [default: 64]
  --pen-clients=PENCLIENTS
                        Max number of connection tracked clients [default:
                        8192]
  --haproxy             Use HAproxy for TCP services instead of running
                        everything through Pen [default: True]
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

Given a Marathon URL, proxymatic will fetch the running tasks and configure proxies that forward connections from the [servicePort](http://mesosphere.com/docs/getting-started/service-discovery/) to the host and port exposed by the task. Proxymatic subscribes to the [Marathon event bus](https://mesosphere.github.io/marathon/docs/event-bus.html) 
and receive cluster changes immediately when they occur, which cuts the response time in case of failover or scaling.

```
docker run --net=host \
  -e MARATHON_URL=http://marathon-host:8080 \
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

```python
import signal
from flask import Flask

app = Flask(__name__)
healthy = True

# Start failing the health check when receiving SIGTERM
def sigterm_handler(_signo, _stack_frame):
  global healthy
  healthy = False

signal.signal(signal.SIGTERM, sigterm_handler)

@app.route('/health')
def health():
  if healthy:
    return 'OK'
  return 'Stopping', 503
```

## Virtual Hosts

The --vhost-domain and $VHOST_DOMAIN parameter can be used to automatically configure an nginx with virtual hosts for each service. This is similar to the [Deis router](http://docs.deis.io/en/latest/understanding_deis/components/#router) component. To use this feature start proxymatic like

```
docker run -p 80:80 -e VHOST_DOMAIN=app.example.com
```

And create a wildcard DNS record that points `*.app.example.com` to the IP of the 
container host. Each service will automatically get a vhost under the app.example.com setup in nginx. For example

| Virtual Host URL   | Marathon Id | Registrator `SERVICE_NAME` |
| :----------------- | :---------- | :----------------------- |
| http://myservice.app.example.com | myservice | myservice |
| http://service.system.product.app.example.com | /product/system/service | service.system.product |

## Application Settings

Applications may set Marathon labels to override load balancer settings for each of their ports, where N = 0..number-of-exposed-ports. For example

```
  "labels": {
    "com.meltwater.proxymatic.0.servicePort": "1234",
    "com.meltwater.proxymatic.0.weight": "100",
    "com.meltwater.proxymatic.0.maxconn": "200",
    "com.meltwater.proxymatic.0.mode": "http"
  }
```

| Label                                          |                                                                                              |
| :--------------------------------------------- | :------------------------------------------------------------------------------------------- |
| com.meltwater.proxymatic.&lt;N&gt;.servicePort | Override the service port for this exposed container port                                    |
| com.meltwater.proxymatic.&lt;N&gt;.weight      | Weight for the containers of this app version in the range `1-1000`. Default value is `500`. |
| com.meltwater.proxymatic.&lt;N&gt;.maxconn     | Maximum concurrent connections per container.                                                |
| com.meltwater.proxymatic.&lt;N&gt;.mode        | Load balancer mode for this port as either `tcp` or `http`. Default is `tcp` mode.           |

Or set Marathon labels to override load balancer settings for the service client or server timeouts. For example

```
  "labels": {
    "com.meltwater.proxymatic.service.timeoutclient": 300,
    "com.meltwater.proxymatic.service.timeoutserver": 300
  }
```

| Label                                          |                                                                                              |
| :--------------------------------------------- | :------------------------------------------------------------------------------------------- |
| com.meltwater.proxymatic.service.timeoutclient | Override the service client timeout (value in seconds)                                       |
| com.meltwater.proxymatic.service.timeoutserver | Override the service server timeout (value in seconds)                                       |


## Deployment

### Graceful Shutdown

The status endpoint which can be used from upstream load balancers to orchestrate graceful restarts
of the Proxymatic container.

* Check the `--status-endpoint` or `$STATUS_ENDPOINT` setting and point your load balancer to the */status* endpoint.
* Ensure that the Docker stop timeout `docker stop --time=seconds` is set higher than the drain timeout used in your load balancer.

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

# Allow docker stop to account for load balancer draining (must be 
# longer than the "--time" parameter of docker stop)
TimeoutStopSec=90

# Restart on failures
KillMode=none
Restart=always
RestartSec=15

ExecStartPre=-/usr/bin/docker kill $NAME
ExecStartPre=-/usr/bin/docker rm $NAME
ExecStartPre=-/usr/bin/docker pull $IMAGE
ExecStart=/usr/bin/docker run --net=host \
    --name=${NAME} \
    -e MARATHON_URL=http://marathon-host:8080 \
    $IMAGE

ExecStop=/usr/bin/docker stop --time=60 $NAME

[X-Fleet]
Global=true
```

### Puppet Hiera

Using the [garethr-docker](https://github.com/garethr/garethr-docker) module

```yaml
classes:
  - docker::run_instance

docker::run_instance:
  'proxymatic':
    image: 'meltwater/proxymatic:latest'
    net: 'host'
    before_stop: '/usr/bin/docker stop --time=60 proxymatic'
    extra_systemd_parameters:
      TimeoutStopSec: 90
    env:
      - "MARATHON_URL=http://marathon-host:8080"
```
