## Deployment

### Frontend Build
```bash
npm run build
```

### Frontend Preview
```bash
npm run preview
```

### Frontend Deployment
- Hosted on Lovable platform
- Automatic deployment on push to main
- Environment variables managed via Lovable dashboard

### Backend Deployment

#### Requirements
- Python 3.9+
- Django 4.x
- Podman (for container orchestration)
- PostgreSQL (production) or SQLite (development)

#### Setup
```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

#### Environment Variables
Create a `.env` file in the `backend` directory:
```
DEBUG=False
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://user:password@host:port/dbname
ALLOWED_HOSTS=your-domain.com
LITEMAAS_BASE_URL=https://your-llm-api-endpoint
LITEMAAS_API_KEY=your-llm-api-key
```

#### Container Deployment
The application can be containerized using the provided `Containerfile`:
```bash
podman build -t projecteverflow .
podman run -p 8000:8000 -p 5173:5173 projecteverflow
```

#### Podman Compose
Use `podman-compose.yml` for multi-container deployment:
```bash
podman-compose up -d
```

This starts:
- Django backend API server
- PostgreSQL database
- Redis (if configured)

#### Production Considerations
- Use ASGI server (Daphne, Uvicorn) for WebSocket support
- Configure NGINX/Apache as reverse proxy
- Enable HTTPS with SSL certificates
- Set up proper logging and monitoring
- Configure CORS for frontend-backend communication
- Enable Django's security middleware
- Use PostgreSQL instead of SQLite
- Configure Podman socket for rootless container management
- Set up persistent volumes for workspace data
- Configure resource limits for workspace containers

### Workspace Management
- Podman must be installed and configured on the host
- Backend needs access to Podman socket (`/run/user/1000/podman/podman.sock`)
- Workspace volumes are persistent across container restarts
- Consider using Podman's volume backup/restore for workspace data

[Back to Index](./index.md)
