# Assignment 5: Infrastructure as Code (IaC) Implementation

## 1. Objective
To provision a reproducible, declarative, and automated cloud infrastructure capable of hosting the Mini E-Commerce microservices application, observing strict Site Reliability Engineering (SRE) practices.

## 2. Terraform Implementation Details

The infrastructure was provisioned using **Terraform** targeting the Hetzner Cloud provider. The configuration ensures that a Virtual Dedicated Server (VDS) with 2 vCPUs and 2GB RAM is automatically spun up perfectly configured to run containerized workloads.

### Key Components

#### 1. `main.tf`
The core configuration file handles the declarative definitions. 
- **Compute Instance**: Uses the `hcloud_server` resource to provision an Ubuntu 22.04 base image on a `cx11` instance type.
- **Security & Networking**: Uses the `hcloud_firewall` resource to implement the principle of least privilege. Only essential ports are open to the internet:
  - Port 80 (HTTP / Nginx Gateway)
  - Port 22 (SSH Access)
  - Port 3000 (Grafana Dashboards)
  - Port 9090 (Prometheus Metrics)
- **Cloud-Init (User Data)**: Contains a bootstrap script passed directly to the VM. On boot, the server automatically installs the Docker Daemon and Docker Compose plugins without any manual intervention.

#### 2. `variables.tf`
Abstracts hardcoded values out of `main.tf` for flexibility across environments. It parametrizes the Datacenter layout (`server_location`), instance size (`server_type`), the SSH Key, and securely handles the cloud API Token via the `sensitive = true` flag.

#### 3. `outputs.tf`
Provides immediate, actionable returns upon a successful `terraform apply`. It outputs the public IP address of the provisioned server, significantly simplifying the developer handoff experience.

## 3. Reproducibility & Deployment Process

The deployment observes immutability. To tear down the server and stand up an identical clone, the process is fully automated via the following standard Terraform workflow:

1. **Initialization**
   ```bash
   terraform init
   ```
   *Downloads the required Hetzner provider configurations and initializes the local backend state.*

2. **Planning**
   ```bash
   terraform plan -var="hcloud_token=<API_TOKEN>" -var="ssh_key_name=<KEY_ID>"
   ```
   *Generates an execution plan, allowing engineers to verify exactly what resources will be created (1 firewall, 1 server) before incurring cloud costs.*

3. **Application**
   ```bash
   terraform apply -auto-approve -var="hcloud_token=<API_TOKEN>" -var="ssh_key_name=<KEY_ID>"
   ```
   *Applies the changes. Outputs the newly provisioned IP address.*

## 4. Architectural Alignment with Requirements
This design strictly fulfills the non-functional goals of the project:
- **Reproducibility**: If the server fails or gets corrupted, we destroy it via `terraform destroy` and rebuild it perfectly in seconds.
- **Automation**: Passing Docker installation scripts via Cloud-Init removes the "manual configuration" anti-pattern.
- **Security**: Port locking at the cloud provider edge layer (before traffic hits the OS via iptables) ensures internal Docker APIs and PostgreSQL ports cannot be exploited externally.
