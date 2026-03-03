# AWS Dashboard Deployment Guide

## Overview

Deploy the trajectory results dashboard to AWS for secure, cloud-based access. Choose the option that best fits your needs:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT OPTIONS                           │
├──────────────────┬───────────┬──────────┬──────────┬────────────┤
│ Option           │ Cost      │ Setup    │ Time     │ Best For   │
├──────────────────┼───────────┼──────────┼──────────┼────────────┤
│ 1. Streamlit    │ $5-15/mo  │ Easy     │ <1 hour  │ Quick      │
│    Cloud        │           │          │          │ launch     │
├──────────────────┼───────────┼──────────┼──────────┼────────────┤
│ 2. EC2 + Nginx  │ $10-30/mo │ Medium   │ 2-3 hrs  │ Private    │
│    (HTTP/HTTPS) │           │          │          │ cloud      │
├──────────────────┼───────────┼──────────┼──────────┼────────────┤
│ 3. ECS Fargate  │ $20-50/mo │ Medium   │ 3-4 hrs  │ Scalable   │
│    (Serverless) │           │          │          │ cloud      │
├──────────────────┼───────────┼──────────┼──────────┼────────────┤
│ 4. QuickSight   │ $30+/mo   │ Hard     │ 4-6 hrs  │ Enterprise │
│    (BI Tool)    │           │          │          │ analytics  │
├──────────────────┼───────────┼──────────┼──────────┼────────────┤
│ 5. Lambda+API   │ <$1/mo*   │ Hard     │ 4-5 hrs  │ Serverless │
│    +S3+CloudFront│           │          │          │ website    │
└──────────────────┴───────────┴──────────┴──────────┴────────────┘

* Pay per request; minimal cost for low traffic
```

---

## OPTION 1: Streamlit Cloud (Easiest - Recommended for MVP)

### 🎯 Best For: Quick launch, sharing with collaborators

### Prerequisites
- GitHub account
- Streamlit Cloud account (free tier available)
- Your code on GitHub

### Step 1: Push Code to GitHub

```bash
cd /home/manoov/Github/aws-healthcare-pipeline

# Initialize git (if not already done)
git init
git add .
git commit -m "Add trajectory dashboard"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/aws-healthcare-pipeline.git
git push -u origin main
```

### Step 2: Connect to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app" → Select your repository
4. **Repository**: `aws-healthcare-pipeline`
5. **Branch**: `main`
6. **Main file path**: `dashboard/trajectory_dashboard.py`
7. Click "Deploy"

### Step 3: (Optional) Configure Secrets

Create `.streamlit/secrets.toml` for AWS credentials:

```toml
[aws]
access_key_id = "YOUR_ACCESS_KEY"
secret_access_key = "YOUR_SECRET_KEY"
region = "us-east-1"
```

### Access the Dashboard

```
https://yourrepo-trajectory-dashboard.streamlit.app
```

### Pros ✅
- Free tier available
- 1-click deployment
- Automatic HTTPS
- Easy sharing via URL

### Cons ❌
- Public by default (needs authentication plugin)
- Limited compute
- Data stored on Streamlit servers
- Not suitable for HIPAA/protected health info

**IMPORTANT**: If using real patient data, this option violates HIPAA. Use Option 2 or 3 instead.

---

## OPTION 2: EC2 + Streamlit + Nginx (Recommended for Production)

### 🎯 Best For: Private cloud deployment with authentication

### Architecture
```
                    Internet
                       ↓
                   Nginx (Reverse Proxy)
                   localhost:80/443
                       ↓
                   Streamlit App
                   localhost:8501
                       ↓
                   [Results Files]
                   [AWS Credentials]
```

### Prerequisites
- AWS Account
- EC2 instance (t3.micro eligible for free tier)
- SSH key pair

### Step 1: Launch EC2 Instance

```bash
# Using AWS CLI
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.micro \
  --region us-east-1 \
  --security-groups default \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=trajectory-dashboard}]'
```

Or use AWS Console:
1. EC2 Dashboard → Instances → Launch Instance
2. **AMI**: Ubuntu Server 22.04 LTS
3. **Instance Type**: t3.micro (free tier)
4. **Security Group**: Allow SSH (22), HTTP (80), HTTPS (443)
5. Download `.pem` key file

### Step 2: SSH into Instance

```bash
chmod 600 your-key.pem
ssh -i your-key.pem ubuntu@your-ec2-public-ip
```

### Step 3: Install Dependencies

```bash
#!/bin/bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python & dependencies
sudo apt-get install -y python3.10 python3-pip python3-venv nginx ssl-cert

# Create app directory
mkdir -p ~/streamlit-app
cd ~/streamlit-app

# Clone your repository
git clone https://github.com/YOUR_USERNAME/aws-healthcare-pipeline.git
cd aws-healthcare-pipeline

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install -r dashboard/requirements.txt
```

### Step 4: Copy Results Data

```bash
# Copy your local results to EC2
scp -i your-key.pem -r ./results ubuntu@your-ec2-ip:~/streamlit-app/aws-healthcare-pipeline/

# Or if already generated on EC2:
cd ~/streamlit-app/aws-healthcare-pipeline
# Run analysis here to generate results
```

### Step 5: Configure Streamlit

Create `~/.streamlit/config.toml`:

```toml
[client]
showErrorDetails = false
showWarningOnDirectExecution = false

[logger]
level = "info"

[server]
port = 8501
headless = true
runOnSave = true
enableXsrfProtection = true

[theme]
primaryColor = "#0066cc"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
```

### Step 6: Configure Nginx (Reverse Proxy)

Create `/etc/nginx/sites-available/trajectory-dashboard`:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Or EC2 public IP
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL Certificates (self-signed for testing, use Let's Encrypt for production)
    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Proxy to Streamlit
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/trajectory-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 7: Create Systemd Service

Create `/etc/systemd/system/streamlit-dashboard.service`:

```ini
[Unit]
Description=Streamlit Trajectory Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/streamlit-app/aws-healthcare-pipeline
ExecStart=/home/ubuntu/streamlit-app/aws-healthcare-pipeline/venv/bin/streamlit run dashboard/trajectory_dashboard.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable streamlit-dashboard
sudo systemctl start streamlit-dashboard
sudo systemctl status streamlit-dashboard  # Check status
```

### Step 8: (Optional) Add Authentication

Create `~/.streamlit/auth.py`:

```python
import streamlit as st

def check_password():
    """Returns `True` if user is authenticated."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state.password_correct = True
            del st.session_state["password"]
        else:
            st.session_state.password_correct = False

    if not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    return True

if __name__ == "__main__":
    if check_password():
        st.write("Welcome!")
    else:
        st.stop()
```

Then in `trajectory_dashboard.py`:

```python
import streamlit as st
from auth import check_password

if not check_password():
    st.stop()

# Rest of app...
```

### Access the Dashboard

```
https://your-ec2-public-ip  (or your-domain.com if DNS configured)
```

### Expected Output

```
                    ┌──────────────────────────────┐
                    │   📊 Trajectory Results      │
                    │      Dashboard Active        │
                    │                              │
                    │   ✅ https://your-ip         │
                    └──────────────────────────────┘
```

### Pros ✅
- Full control & customization
- Private cloud (HIPAA compliant)
- Can add authentication
- Secure HTTPS
- Own data

### Cons ❌
- Requires server management
- Need to manage SSL certificates
- More setup time

---

## OPTION 3: ECS Fargate (Serverless - Scalable)

### 🎯 Best For: Production deployments, auto-scaling

### One-Command Deployment

```bash
# 1. Create ECR repository
aws ecr create-repository --repository-name trajectory-dashboard --region us-east-1

# 2. Build Docker image
cd /home/manoov/Github/aws-healthcare-pipeline
docker build -f dashboard/Dockerfile -t trajectory-dashboard .

# 3. Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker tag trajectory-dashboard:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trajectory-dashboard:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trajectory-dashboard:latest

# 4. Create ECS Cluster
aws ecs create-cluster --cluster-name trajectory --region us-east-1

# 5. Create Task Definition (see dashboard/ecs-task-definition.json)
aws ecs register-task-definition --cli-input-json file://dashboard/ecs-task-definition.json

# 6. Create Service
aws ecs create-service \
  --cluster trajectory \
  --service-name trajectory-dashboard \
  --task-definition trajectory-dashboard:1 \
  --desired-count 1 \
  --launch-type FARGATE
```

See **ECS_DEPLOYMENT.md** for detailed instructions and Docker files.

---

## OPTION 4: AWS QuickSight (Enterprise BI)

### 🎯 Best For: Executive dashboards, advanced analytics

### Setup Steps

1. **Enable QuickSight** in AWS Account
2. **Connect Data Source**:
   - S3 bucket containing results CSV files
   - Or RDS/DynamoDB with trajectory data
3. **Create Visualizations**:
   - Class distribution pie chart
   - Responder/non-responder bar chart
   - AUROC comparison chart
   - Feature heatmap
4. **Create Dashboard** and share with clinicians

See **QUICKSIGHT_SETUP.md** for detailed BI instructions.

---

## OPTION 5: Serverless Website (Lambda + S3 + CloudFront)

### 🎯 Best For: Static/semi-static reports, ultra-low cost

Deploy as **static HTML** + **Lambda API**:

1. Generate HTML report locally
2. Upload to S3
3. Serve via CloudFront CDN
4. Add Lambda backend for dynamic data

See **SERVERLESS_DEPLOYMENT.md** for instructions.

---

## Recommended Path

### For Development (This Week)
```
Option 1: Streamlit Cloud
└─ Deploy in <1 hour
└─ Share URL with team
└─ Test locally first!
```

### For Clinical Review (Next Week)
```
Option 2: EC2 + Streamlit + Nginx
└─ More secure & HIPAA-compliant
└─ Add password authentication
└─ Use real patient data safely
```

### For Production (Following Week)
```
Option 3: ECS Fargate
└─ Auto-scaling & reliability
└─ Load balancing built-in
└─ Production-grade infrastructure
```

---

## Quick Comparison Table

| Feature | Cloud | EC2 | Fargate | QuickSight | Serverless |
|---------|-------|--------|--------|------------|-----------|
| **Cost** | $5-15 | $10-30 | $20-50 | $30+ | <$1 |
| **Setup Time** | <1h | 2-3h | 3-4h | 4-6h | 4-5h |
| **HIPAA Ready** | ❌ | ✅ | ✅ | ✅ | ⚠️ |
| **Authentication** | 🔴 | ✅ | ✅ | ✅ | ⚠️ |
| **Scalability** | Limited | Manual | ✅ | ✅ | ✅ |
| **Customization** | Limited | ✅ | ✅ | Limited | ✅ |

---

## Dashboard Features

All deployments include:

### 📈 Overview Tab
- Total patients & cohort breakdown
- Responder/non-responder distribution
- Trajectory class enrollment
- Key findings summary

### 📊 Statistical Analysis Tab
- Chi-square test results
- AUROC comparison (trajectory vs SOFA)
- DeLong test p-values
- Clinical interpretation

### 🔬 Feature Analysis Tab
- Descriptive statistics (mean ± SD)
- Feature correlation heatmap
- Distribution charts

### 📋 Patient Data Tab
- Filterable patient list
- Trajectory class assignments
- Download CSV export

### 📄 Report Tab
- Formatted clinical report
- Export to PDF
- Summary for publications

---

## Security Best Practices

### For Production Deployment

1. **Authentication**
   - Use IAM roles (AWS services)
   - Use Cognito (users)
   - Use password + 2-factor for dashboard

2. **Encryption**
   - TLS 1.2+ for all traffic
   - Encrypt data at rest (S3)
   - Encrypt AWS credentials

3. **Access Control**
   - Restrict to specific IPs (clinic network)
   - Use VPC security groups
   - Enable CloudTrail logging

4. **Data Protection**
   - De-identify patient data
   - Use synthetic data for demos
   - Audit access logs

### Example: Restricted Access

```bash
# Only allow access from clinic IP
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 443 \
  --cidr 203.0.113.0/32  # Your clinic public IP
```

---

## Troubleshooting

### "Streamlit not loading"
```bash
# Check if service is running
sudo systemctl status streamlit-dashboard

# View logs
sudo journalctl -u streamlit-dashboard -f
```

### "Results files not found"
```bash
# Make sure results directory exists
ls -la ~/streamlit-app/aws-healthcare-pipeline/results/

# Copy if missing
scp -i key.pem -r ./results ubuntu@ec2-ip:~/streamlit-app/...
```

### "Cannot connect to HTTP"
```bash
# Check Nginx status
sudo systemctl status nginx

# Test Nginx config
sudo nginx -t

# Restart
sudo systemctl restart nginx
```

---

## Next Steps

1. **Choose deployment option** above
2. **Follow step-by-step guide** for your choice
3. **Test locally first**:
   ```bash
   streamlit run dashboard/trajectory_dashboard.py
   ```
4. **Deploy to AWS**
5. **Share dashboard URL** with doctor
6. **Collect feedback** for improvements

---

## Support Files

- **dashboard/trajectory_dashboard.py** - Main dashboard code
- **dashboard/requirements.txt** - Python dependencies
- **dashboard/Dockerfile** - Docker image (for ECS)
- **dashboard/ecs-task-definition.json** - ECS config
- **dashboard/.streamlit/config.toml** - Streamlit settings

---

**Questions?** See **AWS_SETUP.md** or contact AWS support.

