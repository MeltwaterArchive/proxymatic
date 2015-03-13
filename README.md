# Proxymatic
The proxymatic image forms one part of a network level service discovery solution. It dynamically configures
proxies that forward network connections to the host where a service is currently running. By subscribing to
events from discovery sources such as [Marathon](https://github.com/mesosphere/marathon) or
[registrator](https://github.com/gliderlabs/registrator) the proxies can quickly be updated whenever a service
is scaled or fails over.

## Configuration Flags
```
docker run docker.meltwater.com/proxymatic:latest --help
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
  docker.meltwater.com/proxymatic:latest
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
