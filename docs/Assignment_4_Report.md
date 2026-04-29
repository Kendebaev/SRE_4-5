# Assignment 4: Incident Response Simulation & Postmortem

## Part 1: Incident Response Simulation

### 1. Incident Summary
At 10:00 AM UTC, the `Order Service` of the Mini E-Commerce platform experienced a complete outage. Users were unable to submit new orders, and the storefront started returning errors when the "Buy Now" button was clicked. The entire transaction flow was halted, resulting in an immediate business impact.

### 2. Impact Assessment & Severity Classification
- **Severity**: SEV-1 (Critical Business Impact)
- **Impact**: 100% of customers attempting to place orders were blocked. Other services (Auth, Product catalog, Chat) remained functional, preventing a complete platform collapse, but the primary revenue-generating action (checkout) was completely down.

### 3. Timeline of Events
- **10:00 AM**: Configuration update deployed to the production `docker-compose.yml` file.
- **10:01 AM**: Prometheus monitoring instantly detected that the `order-service` /metrics endpoint was down. 
- **10:02 AM**: Grafana alerts triggered due to a spike in HTTP 503 Service Unavailable errors on the order API.
- **10:05 AM**: SRE on-call engineer pulled the Docker logs for the `order-service` container using `docker compose logs order`.
- **10:08 AM**: Root cause identified: The SQLAlchemy database connection was timing out as it was trying to reach `db_wrong_host` instead of the internal `postgres` container.
- **10:10 AM**: SRE modified `docker-compose.yml`, reverting `DATABASE_URL` to the correct internal hostname.
- **10:12 AM**: `docker compose up -d order` executed to recreate the container.
- **10:13 AM**: Healthchecks passed. Prometheus target returned to the "UP" state. Service fully restored.

### 4. Root Cause Analysis
The failure was traced back to human error during an environmental configuration update. An engineer accidentally modified the `DATABASE_URL` environment variable within the orchestrator configuration (`docker-compose.yml`) for the `order` service, pointing it to an unresolvable hostname (`db_wrong_host`). 

### 5. Mitigation Steps
1. The immediate mitigation was to rollback the environment configuration to the last known healthy state.
2. The `order` service container was restarted to map the corrected environment variables.

### 6. Resolution Confirmation
System functionality was verified through three methods:
1. **Metrics**: Grafana confirmed that HTTP 5xx errors dropped to zero and HTTP 2xx successful requests resumed.
2. **Health Endpoints**: `curl http://localhost/api/orders/health` returned a `200 OK` and `{"status": "healthy"}`.
3. **End-to-End Test**: A manual test item was placed via the Storefront interface, successfully persisting an order to PostgreSQL.

---

## Part 2: Postmortem Analysis

### 1. Incident Overview
A misconfiguration in the `order-service` environment variables led to a failure to connect to the backend PostgreSQL database, resulting in a 13-minute outage of the checkout system.

### 2. Customer Impact
During the 13-minute window, any customer attempting to purchase items received a generic "Service unavailable" error. We estimate an order drop rate of approximately 25 missed orders over this period. 

### 3. Detection and Response Evaluation
- **What went well**: The observability stack (Prometheus and Grafana) worked perfectly. The `/health` endpoint correctly executed a simulated query (`SELECT 1`), ensuring that the database connection failure immediately translated into an HTTP 503 error that Prometheus scraped and detected.
- **What needs improvement**: The faulty configuration was deployed directly to the "production" Docker Compose setup without prior validation or testing. 

### 4. Lessons Learned
- Storing hardcoded environmental URLs directly inside `docker-compose.yml` is prone to human error. Secrets and configuration strings should be centralized in external secure `.env` files.
- We need automated integration tests that run *before* new containers are spun up in the orchestrator.

### 5. Action Items
| Action Item | Owner | Priority | Status |
|-------------|-------|----------|--------|
| Move all `DATABASE_URL` assignments out of compose and strictly into `.env`. | DevOps | High | Pending |
| Add a `docker-compose config` infrastructure check to the CI pipeline to catch syntax errors before deployment. | SRE | Medium | Pending |
| Implement a generic "Fail Whale" error screen on the frontend for graceful degradation instead of raw JS alerts. | Frontend | Low | Pending |
