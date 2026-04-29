# Incident Simulation: Database Outage on Order Service

This guide explains how to intentionally trigger an outage in the **Order Service**, demonstrating how the observability stack (Prometheus & Grafana) detects and visualizes the failure. 

## 1. Baseline Verification

Before starting the simulation, ensure the system is healthy.

1. Open your browser and go to the **Storefront** (Nginx Gateway). 
2. Click **Buy Now** to confirm the Order Service is currently working (you should get an alert saying "Order successful!").
3. Navigate to **Prometheus** at `http://<server-ip>:9090/targets`. Verify that the `order-service` target is in the **UP** state.
4. Optional: In **Grafana** (`http://<server-ip>:3000`), check the incoming HTTP requests graph for the Order Service.

---

## 2. Inject Fault

We will simulate a configuration drift or network failure by pointing the Order Service to a non-existent database host.

1. Open the `docker-compose.yml` file.
2. Under the `order` service, locate the `environment` section.
3. Modify the `DATABASE_URL` line:
   
   **Change from:**
   ```yaml
   - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-appuser}:${POSTGRES_PASSWORD:-supersecurepassword}@postgres:5432/${POSTGRES_DB:-ecommerce_db}
   ```
   **To:**
   ```yaml
   - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-appuser}:${POSTGRES_PASSWORD:-supersecurepassword}@db_wrong_host:5432/${POSTGRES_DB:-ecommerce_db}
   ```

## 3. Apply the Change

Restart only the `order` service to apply the faulty environment variable:

```bash
docker compose up -d order
```

---

## 4. Observe the Failure

1. **User Impact**: 
   Go to the Storefront and click **Buy Now** again. It will fail.
   
2. **Health Check Failure**:
   Curl the health endpoint (which explicitly checks the DB connection):
   ```bash
   curl -i http://localhost/api/orders/health
   ```
   *Expected Output*: HTTP 503 Service Unavailable, `{"status": "unhealthy", "error": "..."}`

3. **Prometheus Detection**:
   Go to `http://<server-ip>:9090/targets`. 
   Within ~15-30 seconds, the target for `order-service` will change from **UP** to **DOWN**.

4. **Logs (Diagnosis)**:
   Investigate why it failed using Docker logs:
   ```bash
   docker compose logs order
   ```
   *Expected Output*: You will see SQLAlchemy connection timeout/resolution errors trying to reach `db_wrong_host`.

---

## 5. Remediate & Recover

Once the incident has been detected and diagnosed, fix the system.

1. Edit the `docker-compose.yml` file and revert the `DATABASE_URL` back to the original value (using `@postgres:5432`).
2. Restart the service:
   ```bash
   docker compose up -d order
   ```
3. **Verify Recovery**:
   - `curl http://localhost/api/orders/health` should return HTTP 200.
   - Prometheus Targets UI should show `order-service` as **UP** again.
   - Clicking **Buy Now** on the Storefront should succeed.
