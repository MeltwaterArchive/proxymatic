# Proxymatic

The proxymatic image forms one part of a network level service discovery solution. It dynamically configures
proxies that forward network connections to the host where a service is currently running. By subscribing to
events from discovery sources such as [Marathon](https://github.com/mesosphere/marathon) or
[registrator](https://github.com/gliderlabs/registrator) the proxies can quickly be updated whenever a service
is scaled or fails over.

## Environment Variables

 * **REGISTRATOR_URL** - URL where registrator publishes services, e.g. "etcd://localhost:4001/services"
 * **MARATHON_URL** - Marathon URL to query, e.g. "http://localhost:8080/"
 * **MARATHON_CALLBACK_URL** - URL to listen for Marathon HTTP callbacks, e.g. "http://localhost:5090/"
 * **REFRESH_INTERVAL=60** - Polling interval when using non-event capable backends. Defaults to 60 seconds.
 * **EXPOSE_HOST=false** - Expose services running in net=host mode. May cause port collisions when this container is also run in net=host mode. Defaults to false.
 * **HAPROXY=false** - Use HAproxy for TCP services instead of running everything through Pen. Defaults to false.
 * **VHOST_DOMAIN** - Enables nginx with virtual hosts for each service under this domain, e.g. "services.example.com"
 * **VHOST_PORT** - Port to serve virtual hosts from. Defaults to port 80.
 * **PROXY_PROTOCOL=false** - Enable proxy protocol on the nginx vhost which is needed when using the AWS ELB in TCP mode for websocket support.

## Command Line Usage

```
Usage: docker run meltwater/proxymatic:latest [options]...

Proxy for TCP/UDP services registered in Marathon and etcd

Options:
  -h, --help            show this help message and exit
  -r REGISTRATOR, --registrator=REGISTRATOR
                        URL where registrator publishes services, e.g. "etcd
                        ://etcd-host:4001/services"
  -m MARATHON, --marathon=MARATHON
                        Marathon URL to query, e.g. "http://marathon-
                        host:8080/"
  -c CALLBACK, --marathon-callback=CALLBACK
                        URL to listen for Marathon HTTP callbacks, e.g.
                        "http://`hostname -f`:5090/"
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

Given a Marathon URL proxymatic will periodically fetch the running tasks and configure proxies that
forward connections from the [servicePort](http://mesosphere.com/docs/getting-started/service-discovery/)
to the host and port exposed by the task. If Marathon is started with 
[HTTP callback support](https://mesosphere.github.io/marathon/docs/event-bus.html) then proxymatic can
be notified immediatly, which cuts the response time in case of failover or scaling.

```
docker run --net=host \
  -e MARATHON_URL=http://marathon-host:8080 \
  -e MARATHON_CALLBACK_URL=http://$(hostname --fqdn):5090 \
  meltwater/proxymatic:latest
```

Given the service below proxymatic will listen on port 1234 and forward connections to port 8080 
inside the container. 

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

## Virtual Hosts

The --vhost-domain and $VHOST_DOMAIN parameter can be used to automatically configure an nginx with 
virtual hosts for each service. This is similar to the [Deis router](http://docs.deis.io/en/latest/understanding_deis/components/#router) component. 
To use this feature start proxymatic like

```
docker run -p 80:80 -e VHOST_DOMAIN=app.example.com
```

And create a wildcard DNS record that points *.app.example.com to the IP of the 
container host. Each service will automatically get a vhost under the app.example.com 
setup in nginx. For example

| Virtual Host URL   | Marathon Id | Registrator SERVICE_NAME |
| :----------------- | :---------- | :----------------------- |
| http://myservice.app.example.com | myservice | myservice |
| http://service.system.product.app.example.com | /product/system/service | service.system.product |

## Deployment

### Systemd and CoreOS/Fleet

Create a [Systemd unit](http://www.freedesktop.org/software/systemd/man/systemd.unit.html) file 
in **/etc/systemd/system/proxymatic.service** with contents like below. Using CoreOS and
[Fleet](https://coreos.com/docs/launching-containers/launching/fleet-unit-files/) then
add the X-Fleet section to schedule the unit on all cluster nodes.

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
