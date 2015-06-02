# Proxymatic

The proxymatic image forms one part of a network level service discovery solution. It dynamically configures
proxies that forward network connections to the host where a service is currently running. By subscribing to
events from discovery sources such as [Marathon](https://github.com/mesosphere/marathon) or
[registrator](https://github.com/gliderlabs/registrator) the proxies can quickly be updated whenever a service
is scaled or fails over.

## Command Line Usage

```
Usage: docker run meltwater/proxymatic:latest [options]...

Proxy for TCP/UDP services registered in Marathon and etcd

Options:
  -h, --help            show this help message and exit
  -r REGISTRATOR, --registrator=REGISTRATOR
                        URL where registrator publishes services, e.g.
                        "etcd://localhost:4001/services"
  -m MARATHON, --marathon=MARATHON
                        Marathon URL to query, e.g. "http://localhost:8080/"
  -c CALLBACK, --marathon-callback=CALLBACK
                        URL to listen for Marathon HTTP callbacks
  -v, --verbose         Increase verbosity
  -i INTERVAL, --refresh-interval=INTERVAL
                        Polling interval when using non-event capable backends
                        [default: 60]
  -e, --expose-host     Expose services running in net=host mode. May cause
                        port collisions when this container is also run in
                        net=host mode [default: False]
  --pen-template=PENTEMPLATE
                        Template pen proxy config file [default:
                        /etc/pen/pen.cfg.tpl]
  --pen-servers=PENSERVERS
                        Max number of backend servers for each pen service
                        [default: 32]
  --pen-clients=PENCLIENTS
                        Max number of pen client connections [default: 8192]
  --pen-user=PENUSER    User to run pen proxy as [default: pen]
  --haproxy             Use HAproxy for TCP services [default: False]
  --haproxy-start=HAPROXYSTART
                        Command to start HAproxy [default: /etc/init.d/haproxy
                        start]
  --haproxy-reload=HAPROXYRELOAD
                        Command to reload HAproxy [default:
                        /etc/init.d/haproxy reload]
  --haproxy-config=HAPROXYCONFIG
                        HAproxy config file to write [default:
                        /etc/haproxy/haproxy.cfg]
  --haproxy-template=HAPROXYTEMPLATE
                        Template HAproxy config file [default:
                        /etc/haproxy/haproxy.cfg.tpl]
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
