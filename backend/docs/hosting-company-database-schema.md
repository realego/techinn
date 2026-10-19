# Hosting Company Database Schema

This is a normalized hosting-commerce + billing + provisioning + automation database design.

## Core philosophy

> Define something once, reference it everywhere.

Prices, services, features, payment providers, email templates, automation rules and configuration should each have one authoritative place.

## 1. Customers

### `customers`

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    uuid CHAR(36) NOT NULL UNIQUE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(50),
    company_name VARCHAR(255),
    password_hash VARCHAR(255),
    status ENUM('active','suspended','disabled','pending') NOT NULL DEFAULT 'pending',
    email_verified_at DATETIME NULL,
    phone_verified_at DATETIME NULL,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_customer_status (status),
    INDEX idx_customer_phone (phone)
);
```

Do not duplicate customer information in orders. Orders reference `customer_id`.

## 2. Service categories

### `service_types`

```sql
CREATE TABLE service_types (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

Examples:

- Web Hosting
- Email Hosting
- Domain Registration
- Website Development
- Application Development

Future services can be added without changing the schema.

## 3. Products

### `products`

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    service_type_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    billing_type ENUM('one_time','recurring','usage') NOT NULL,
    status ENUM('draft','active','inactive','archived') NOT NULL DEFAULT 'draft',
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (service_type_id) REFERENCES service_types(id),
    UNIQUE KEY uq_product_service_name (service_type_id, name),
    INDEX idx_product_service (service_type_id, status)
);
```

Example:

```text
Web Hosting
├── Starter
├── Business
└── Professional

Email Hosting
├── Basic Mail
├── Business Mail
└── Enterprise Mail
```

## 4. Pricing

### `product_prices`

```sql
CREATE TABLE product_prices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT UNSIGNED NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    billing_interval ENUM(
        'one_time',
        'monthly',
        'quarterly',
        'semi_annually',
        'annually',
        'biennially',
        'custom'
    ) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    setup_fee DECIMAL(12,2) NOT NULL DEFAULT 0,
    trial_days INT NOT NULL DEFAULT 0,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE KEY uq_product_price (product_id, currency, billing_interval)
);
```

Pricing is configured in one place.

Example:

```text
Business Hosting
├── USD Monthly    $5
├── USD Annual     $50
└── USD Biennial   $90
```

## 5. Features

### `features`

```sql
CREATE TABLE features (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    slug VARCHAR(150) NOT NULL UNIQUE,
    data_type ENUM('text','number','boolean','storage','json') NOT NULL DEFAULT 'text',
    description TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

Examples:

- Storage
- Bandwidth
- Email Accounts
- Databases
- Domains
- CPU
- RAM
- SSL
- Backups
- FTP Accounts

## 6. Product features

### `product_features`

```sql
CREATE TABLE product_features (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT UNSIGNED NOT NULL,
    feature_id BIGINT UNSIGNED NOT NULL,
    value_text TEXT NULL,
    value_number DECIMAL(20,4) NULL,
    value_boolean BOOLEAN NULL,
    value_json JSON NULL,
    display_value VARCHAR(255),
    sort_order INT NOT NULL DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (feature_id) REFERENCES features(id) ON DELETE CASCADE,
    UNIQUE KEY uq_product_feature (product_id, feature_id)
);
```

Example:

```text
Business Hosting
├── Storage = 20 GB
├── Bandwidth = Unlimited
├── Email Accounts = 20
└── Databases = 5
```

## 7. Add-ons

### `addons`

```sql
CREATE TABLE addons (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    billing_type ENUM('one_time','recurring') NOT NULL,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### `addon_prices`

```sql
CREATE TABLE addon_prices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    addon_id BIGINT UNSIGNED NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    billing_interval ENUM('one_time','monthly','quarterly','annually') NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (addon_id) REFERENCES addons(id) ON DELETE CASCADE,
    UNIQUE KEY uq_addon_price (addon_id, currency, billing_interval)
);
```

### `product_addons`

```sql
CREATE TABLE product_addons (
    product_id BIGINT UNSIGNED NOT NULL,
    addon_id BIGINT UNSIGNED NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, addon_id),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (addon_id) REFERENCES addons(id) ON DELETE CASCADE
);
```

One add-on can therefore be reused across multiple services.

## 8. Orders

### `orders`

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    uuid CHAR(36) NOT NULL UNIQUE,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_number VARCHAR(50) NOT NULL UNIQUE,
    status ENUM(
        'pending',
        'awaiting_payment',
        'paid',
        'processing',
        'completed',
        'cancelled',
        'failed'
    ) NOT NULL DEFAULT 'pending',
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
    discount_total DECIMAL(12,2) NOT NULL DEFAULT 0,
    tax_total DECIMAL(12,2) NOT NULL DEFAULT 0,
    total DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX idx_orders_customer (customer_id),
    INDEX idx_orders_status (status)
);
```

## 9. Order items

### `order_items`

```sql
CREATE TABLE order_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NULL,
    addon_id BIGINT UNSIGNED NULL,
    description VARCHAR(255) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(12,2) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL,
    metadata JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (addon_id) REFERENCES addons(id),
    INDEX idx_order_items_order (order_id)
);
```

Order prices are snapshots. If a product changes from $10 to $15 later, an existing order remains $10.

## 10. Customer services

An order records what was purchased. A customer service records what the customer currently owns.

### `customer_services`

```sql
CREATE TABLE customer_services (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    uuid CHAR(36) NOT NULL UNIQUE,
    customer_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_item_id BIGINT UNSIGNED NULL,
    status ENUM(
        'pending',
        'provisioning',
        'active',
        'suspended',
        'expired',
        'cancelled',
        'terminated',
        'failed'
    ) NOT NULL DEFAULT 'pending',
    started_at DATETIME NULL,
    expires_at DATETIME NULL,
    next_due_at DATETIME NULL,
    auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
    cancelled_at DATETIME NULL,
    provisioning_data JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (order_item_id) REFERENCES order_items(id),
    INDEX idx_customer_services_customer (customer_id),
    INDEX idx_customer_services_expiry (status, expires_at),
    INDEX idx_customer_services_due (status, next_due_at)
);
```

## 11. Service-specific data

Different services need different data, so do not pollute `customer_services` with fields such as `domain_name`, `hosting_username`, `server_ip` and `website_url`.

### `service_instances`

```sql
CREATE TABLE service_instances (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_service_id BIGINT UNSIGNED NOT NULL,
    instance_type VARCHAR(100) NOT NULL,
    external_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    data JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_service_id) REFERENCES customer_services(id) ON DELETE CASCADE,
    UNIQUE KEY uq_service_instance (customer_service_id, instance_type)
);
```

Example domain data:

```json
{
  "domain": "example.co.zw",
  "registrar": "some-registrar",
  "nameservers": [
    "ns1.example.com",
    "ns2.example.com"
  ]
}
```

Example hosting data:

```json
{
  "server": "srv01",
  "username": "client123",
  "cpanel_id": "92881"
}
```

## 12. Invoices

### `invoices`

```sql
CREATE TABLE invoices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    status ENUM(
        'draft',
        'unpaid',
        'partially_paid',
        'paid',
        'overdue',
        'cancelled'
    ) NOT NULL DEFAULT 'draft',
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
    tax_total DECIMAL(12,2) NOT NULL DEFAULT 0,
    total DECIMAL(12,2) NOT NULL DEFAULT 0,
    amount_paid DECIMAL(12,2) NOT NULL DEFAULT 0,
    due_at DATETIME NULL,
    paid_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX idx_invoice_customer (customer_id),
    INDEX idx_invoice_status (status),
    INDEX idx_invoice_due (due_at)
);
```

### `invoice_items`

```sql
CREATE TABLE invoice_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    invoice_id BIGINT UNSIGNED NOT NULL,
    customer_service_id BIGINT UNSIGNED NULL,
    product_id BIGINT UNSIGNED NULL,
    addon_id BIGINT UNSIGNED NULL,
    description VARCHAR(255) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(12,2) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_service_id) REFERENCES customer_services(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (addon_id) REFERENCES addons(id)
);
```

## 13. Payment providers

Do not hard-code PayNow into the payment tables.

### `payment_providers`

```sql
CREATE TABLE payment_providers (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    provider_type VARCHAR(50) NOT NULL,
    status ENUM('active','inactive','maintenance') NOT NULL DEFAULT 'active',
    configuration JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

Possible providers:

- PayNow
- EcoCash
- OneMoney
- InnBucks
- Bank Transfer
- Card

Payment credentials should preferably be encrypted or stored in a secrets system rather than plain JSON.

## 14. Payments

### `payments`

```sql
CREATE TABLE payments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    uuid CHAR(36) NOT NULL UNIQUE,
    customer_id BIGINT UNSIGNED NOT NULL,
    invoice_id BIGINT UNSIGNED NULL,
    payment_provider_id BIGINT UNSIGNED NOT NULL,
    reference VARCHAR(255) NOT NULL,
    provider_reference VARCHAR(255),
    amount DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status ENUM(
        'pending',
        'processing',
        'successful',
        'failed',
        'cancelled',
        'expired',
        'refunded'
    ) NOT NULL DEFAULT 'pending',
    initiated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    provider_data JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (payment_provider_id) REFERENCES payment_providers(id),
    UNIQUE KEY uq_provider_reference (payment_provider_id, provider_reference),
    INDEX idx_payment_status (status),
    INDEX idx_payment_reference (reference)
);
```

## 15. Payment attempts and polling

This supports PayNow initiation, polling, callbacks, verification and refunds.

### `payment_attempts`

```sql
CREATE TABLE payment_attempts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    payment_id BIGINT UNSIGNED NOT NULL,
    attempt_number INT NOT NULL,
    request_type ENUM(
        'initiate',
        'poll',
        'callback',
        'verify',
        'refund'
    ) NOT NULL,
    request_data JSON NULL,
    response_data JSON NULL,
    status VARCHAR(50),
    attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    next_poll_at DATETIME NULL,
    completed_at DATETIME NULL,
    FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE CASCADE,
    UNIQUE KEY uq_payment_attempt (payment_id, attempt_number),
    INDEX idx_payment_poll (next_poll_at, status)
);
```

A worker can process due polls:

```sql
SELECT *
FROM payment_attempts
WHERE next_poll_at <= NOW()
AND status = 'pending';
```

## 16. Payment events

### `payment_events`

```sql
CREATE TABLE payment_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    payment_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    provider_status VARCHAR(100),
    payload JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE CASCADE,
    INDEX idx_payment_events (payment_id, created_at)
);
```

This gives you an immutable payment history.

## 17. Email system

Do not create separate tables such as `otp_emails`, `invoice_emails`, `password_emails` and `expiry_emails`.

Everything becomes a reusable email template.

### `email_templates`

```sql
CREATE TABLE email_templates (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(150) NOT NULL UNIQUE,
    subject VARCHAR(255) NOT NULL,
    body_html LONGTEXT NOT NULL,
    body_text LONGTEXT NULL,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

Examples:

- welcome_email
- verify_email
- login_otp
- password_reset
- invoice_created
- payment_received
- payment_failed
- service_activated
- service_expiring
- service_expired
- domain_expiring

## 18. Email variables

### `email_template_variables`

```sql
CREATE TABLE email_template_variables (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email_template_id BIGINT UNSIGNED NOT NULL,
    variable_name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    required BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (email_template_id) REFERENCES email_templates(id) ON DELETE CASCADE,
    UNIQUE KEY uq_template_variable (email_template_id, variable_name)
);
```

Examples:

```text
{{customer_name}}
{{invoice_number}}
{{amount}}
{{service_name}}
{{expiry_date}}
{{verification_code}}
{{reset_link}}
```

## 19. Email queue

### `email_queue`

```sql
CREATE TABLE email_queue (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT UNSIGNED NULL,
    email_template_id BIGINT UNSIGNED NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    payload JSON NOT NULL,
    status ENUM(
        'pending',
        'processing',
        'sent',
        'failed',
        'cancelled'
    ) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    scheduled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME NULL,
    last_error TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (email_template_id) REFERENCES email_templates(id),
    INDEX idx_email_queue (status, scheduled_at)
);
```

Flow:

```text
Trigger
  ↓
Email template
  ↓
email_queue
  ↓
Worker / cron
  ↓
Email provider
  ↓
sent / failed
```

## 20. Email logs

### `email_logs`

```sql
CREATE TABLE email_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email_queue_id BIGINT UNSIGNED NOT NULL,
    provider VARCHAR(100),
    provider_message_id VARCHAR(255),
    status ENUM(
        'sent',
        'delivered',
        'bounced',
        'complained',
        'failed'
    ) NOT NULL,
    response_data JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (email_queue_id) REFERENCES email_queue(id) ON DELETE CASCADE
);
```

## 21. Automation rules

### `automation_rules`

```sql
CREATE TABLE automation_rules (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(150) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    offset_value INT NULL,
    offset_unit ENUM(
        'minutes',
        'hours',
        'days',
        'weeks',
        'months'
    ) NULL,
    direction ENUM('before','after','at') NULL,
    action_type VARCHAR(100) NOT NULL,
    configuration JSON NULL,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

Example:

```text
Domain expiry reminder

event:
service.expiring

offset:
30 days before

action:
send_email

configuration:
{
    "template": "domain_expiring"
}
```

Another rule can be:

```text
Hosting expiry reminder
10 days before
send_email
```

The same engine handles both.

## 22. Automation executions

This prevents duplicate execution.

### `automation_executions`

```sql
CREATE TABLE automation_executions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    automation_rule_id BIGINT UNSIGNED NOT NULL,
    customer_service_id BIGINT UNSIGNED NULL,
    customer_id BIGINT UNSIGNED NULL,
    scheduled_for DATETIME NOT NULL,
    executed_at DATETIME NULL,
    status ENUM(
        'pending',
        'processing',
        'completed',
        'failed',
        'skipped'
    ) NOT NULL DEFAULT 'pending',
    result JSON NULL,
    FOREIGN KEY (automation_rule_id) REFERENCES automation_rules(id),
    FOREIGN KEY (customer_service_id) REFERENCES customer_services(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    UNIQUE KEY uq_automation_execution (
        automation_rule_id,
        customer_service_id,
        scheduled_for
    ),
    INDEX idx_automation_pending (status, scheduled_for)
);
```

Cron/worker:

```sql
SELECT *
FROM automation_executions
WHERE status = 'pending'
AND scheduled_for <= NOW();
```

## 23. Generic application events

### `system_events`

```sql
CREATE TABLE system_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(150) NOT NULL,
    customer_id BIGINT UNSIGNED NULL,
    customer_service_id BIGINT UNSIGNED NULL,
    entity_type VARCHAR(100),
    entity_id BIGINT UNSIGNED,
    payload JSON,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (customer_service_id) REFERENCES customer_services(id),
    INDEX idx_event_processing (processed, created_at),
    INDEX idx_event_type (event_type)
);
```

Useful events include:

```text
customer.created
customer.login
customer.password_reset_requested

order.created
order.paid
order.cancelled

payment.initiated
payment.successful
payment.failed

service.created
service.activated
service.expiring
service.expired
service.suspended

invoice.created
invoice.paid
invoice.overdue
```

## 24. General configuration

### `settings`

```sql
CREATE TABLE settings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(150) NOT NULL UNIQUE,
    value TEXT,
    value_type ENUM(
        'string',
        'integer',
        'decimal',
        'boolean',
        'json'
    ) NOT NULL DEFAULT 'string',
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    description VARCHAR(255),
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

Examples:

```text
company.name
company.email
company.phone
billing.default_currency
billing.invoice_due_days
payments.default_provider
email.from_address
email.from_name
automation.worker_interval
```

Do not use `settings` for data that deserves a proper relational table.

# Overall architecture

```text
                         ┌──────────────┐
                         │  customers   │
                         └──────┬───────┘
                                │
               ┌────────────────┼─────────────────┐
               │                │                 │
               ▼                ▼                 ▼
          ┌─────────┐      ┌──────────┐      ┌──────────┐
          │ orders  │      │ invoices │      │ payments │
          └────┬────┘      └────┬─────┘      └────┬─────┘
               │                │                 │
               ▼                ▼                 ▼
        ┌────────────┐    ┌─────────────┐   ┌────────────────┐
        │ order_items│    │invoice_items│   │payment_attempts│
        └─────┬──────┘    └─────────────┘   └────────────────┘
              │
              ▼
      ┌─────────────────┐
      │customer_services│
      └────────┬────────┘
               │
               ▼
      ┌─────────────────┐
      │service_instances│
      └─────────────────┘


                  PRODUCT CATALOG

       ┌───────────────┐
       │ service_types │
       └───────┬───────┘
               │
               ▼
          ┌──────────┐
          │ products │
          └────┬─────┘
               │
        ┌──────┴──────────┐
        ▼                 ▼
 ┌──────────────┐   ┌────────────────┐
 │product_prices│   │product_features│
 └──────────────┘   └───────┬────────┘
                            │
                            ▼
                       ┌──────────┐
                       │ features │
                       └──────────┘

             ADDONS
                │
                ▼
             addons
                │
                ▼
          addon_prices
                │
                ▼
          product_addons


                  AUTOMATION

        ┌────────────────────┐
        │ automation_rules   │
        └─────────┬──────────┘
                  ▼
        ┌─────────────────────┐
        │automation_executions│
        └─────────────────────┘


                    EMAIL

        ┌─────────────────┐
        │ email_templates │
        └────────┬────────┘
                 │
        ┌────────┴─────────────┐
        ▼                      ▼
 template_variables       email_queue
                                │
                                ▼
                           email_logs
```

# Core conceptual separation

These four concepts should remain distinct:

### Product

What do you sell?

```text
Business Hosting
```

### Price

How much does it cost?

```text
$29.99 / year
```

### Order

What did the customer purchase?

```text
Order #10025
```

### Service

What does the customer currently have?

```text
Business Hosting
Active
Expires 2027-10-08
```

That separation prevents many billing-system problems.

# Payment flow

```text
Customer
   │
   ▼
Checkout
   │
   ▼
Order created
   │
   ▼
Invoice created
   │
   ▼
Payment created
   │
   ▼
PayNow initiation
   │
   ▼
payment_attempts
   │
   ▼
Background worker
   │
   ├── poll
   ├── poll
   ├── poll
   └── poll
         │
         ▼
   Payment successful
         │
         ▼
   payment.status = successful
         │
         ▼
   invoice.status = paid
         │
         ▼
   order.status = paid
         │
         ▼
   customer_service = active
         │
         ▼
   system_event
   "service.activated"
         │
         ├───────────────┐
         ▼               ▼
   provisioning     email queue
```

This is safer than having the payment endpoint directly activate everything.

# Expiry automation

For a domain:

```text
service.expires_at
       │
       ▼
automation rule
"30 days before"
       │
       ▼
automation execution
       │
       ▼
email queue
       │
       ▼
domain_expiring template
       │
       ▼
customer email
```

For hosting, use the same engine with a different rule such as "10 days before".

# Provisioning architecture

Because this is a hosting company, keep provisioning separate from the billing database:

```text
                BILLING DATABASE
                       │
                       ▼
                 system_events
                       │
                       ▼
              ┌────────────────┐
              │ Service Worker │
              └───────┬────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
   cPanel/WHM      Registrar       Mail Server
   API             API             API
```

The database does not need to know how cPanel, CyberPanel, a registrar or a mail server works.

It says what needs to happen, and the appropriate worker handles it.

# Recommended backend direction

Keep the existing UI unchanged. Make the backend expose a clean API around:

```text
catalog
   ↓
cart / order
   ↓
invoice
   ↓
payment
   ↓
service
   ↓
provisioning
   ↓
automation
   ↓
notification
```

The UI becomes a consumer of normalized resources rather than containing the business rules itself.
