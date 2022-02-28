# Configure Determined with Prometheus and Grafana
Setting up Prometheus/Grafana monitoring tools for Determined

| Supported Versions |
| :---: |
  Grafana 7.5.0+
  Prometheus 2.14.0
  Determined 0.17.8+

This document describes the setup and configuration needed to enable a Grafana dashboard to monitor hardware and system metrics on a cloud cluster, such as AWS or Kubernetes, running Determined. Determined provides a Prometheus endpoint containing mappings between internal task, GPU, and container definitions which is used by Prometheus to collect relevant metrics on a cluster running Determined. The endpoint is not enabled by default but can be enabled in the master configuration. 


## Reference

[Grafana](https://grafana.com/docs/grafana/latest/installation/)

[Prometheus](https://prometheus.io/docs/prometheus/latest/installation/)

[cAdvisor](https://github.com/google/cadvisor/blob/master/docs/storage/prometheus.md)

[dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter)


## Constraints
The Determined Prometheus endpoint is configured to work with cAdvisor for CPU metrics and DCGM for GPU metrics. Although other monitoring tools can be used with the setup, this guide details only cAdvisor and DCGM tool configuration. Prometheus queries on metrics collected by other tools can differ depending on the format and organization of the returned metrics. 

## Prerequisites
- Grafana installation for dashboard monitoring
- An on-cluster Prometheus instance for time-series data collection


## Configure Determined
Install and run Determined on a cluster. When launching the master instance, enable the Prometheus endpoint by adding a flag to the `master.yaml` configuration: 
```
observability:
    enable_prometheus: true
```
This presents the following two Prometheus API endpoints on the instance. 

### {$DET_MASTER_ADDR}/prom/det-state-metrics

The `det-state-metrics` endpoint includes various machine-level labels mappings, including GPU UUIDs and container IDs, to internal Determined entities, such as task, allocation, and experiment labels, used by PromQL to join vectors. 

### {$DET_MASTER_ADDR}/prom/det-http-sd-config
The `det-http-sd-config` endpoint contains address and resource pool information for currently active agents, which are used by Prometheus as targets for scraping. This endpoint is configured to support running default cAdvisor, port 8080, and DCGM, port 9400, monitoring. Other tools exposing Prometheus metrics can be used instead of cAdvisor and DCGM if they are running on these ports. 


## Configure cAdvisor and dcgm-exporter
cAdvisor and dcgm-exporter must be running on the cluster agents to be monitored. This can be installed manually or run as individual Docker containers.

The cAdvisor and dcgm-exporter tools must be running on the cluster agents that are monitored. These can be installed manually or run as individual Docker containers. 

To configure dynamic agents to start up with cAdvisor and dcgm-exporter, a startup script can be added to `master.yaml`: 
```
- pool_name: compute-pool
    provider:
      startup_script: |
        # Run dcgm-exporter on 9400
        docker run -d --gpus all --rm -p 9400:9400 nvcr.io/nvidia/k8s/dcgm-exporter:2.3.2-2.6.3-ubuntu20.04

        # Run cAdvisor on 8080
        VERSION=v0.36.0
        docker run \
          --volume=/:/rootfs:ro \
          --volume=/var/run:/var/run:ro \
          --volume=/sys:/sys:ro \
          --volume=/var/lib/docker/:/var/lib/docker:ro \
          --volume=/dev/disk/:/dev/disk:ro \
          --publish=8080:8080 \
          --detach=true \
          --name=cadvisor \
          --privileged \
          --device=/dev/kmsg \
          gcr.io/cadvisor/cadvisor:$VERSION
```
 

In the pool configuration section of `master.yaml`, a startup script parameter can be added to run a script on agent startup. This sample startup script includes the default setup docker commands provided by [dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter) and [cAdvisor](https://github.com/google/cadvisor). 

## Configure Prometheus
[Install Prometheus](https://prometheus.io/docs/prometheus/latest/installation/) on any node in the monitored cluster.

Launch Prometheus with the [provided prometheus.yml configuration](prometheus.yml).
> Tip
> - The `metric_relabel_configs` parameter edits certain label names in jobs for joining in PromQL.
> - The `scrape_interval` parameter values can be modified to optimize for resolution/size/time. 

## Configure Grafana
A Grafana instance can be installed on any machine that adds the above Prometheus address as a data source. Once a Grafana server is running and the Web UI is accessible, follow these steps:
1. Add a Prometheus data source
Under Grafana -> Configuration -> Data Sources -> Add data source, configure the Prometheus data source setup in the previous section by setting the URL to the address of your running Prometheus server. By default, this will be the machine address on port 9090.
2. Once the Prometheus data source is connected, import the [Determined Hardware Metrics dashboard JSON](determined-hardware-grafana.json) under Grafana -> Create -> Import -> Import via panel json.

## Example
After following the above steps and submitting some experiments on the cluster, you should see populated panels in the imported Grafana dashboard (Grafana -> Dashboards).

![Sample Dashboard](grafana-example.png)

Each panel in the dashboard is powered by one or more Prometheus queries and tracks a specific metric on the cluster as a percentage of its total capacity. Results can be further filtered by `tags` and `resource pool` as well as time range in Grafana. 