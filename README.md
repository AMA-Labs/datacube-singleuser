# datacube
Container based datacube implementation

# Prerequisites
- Rancher Desktop or Podman or Docker

# Description
Builds a container with the datacube toolset built in.

# Getting Started
1. Build the container:
```Shell
nerdctl build -t datacube -f Dockerfile
```
2. Run the container:
```Shell
nerdctl run --rm -it \
-e DB_DATABASE=datacube \
-e DB_HOSTNAME=db \
-e DB_USERNAME=datacube \
-e DB_PASSWORD=supersecretpassword \
-e DB_PORT=5432 \
datacube bash
```