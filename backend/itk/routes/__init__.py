from itk.routes import health, oauth, pipeline, public, webhooks

ROUTERS = (health.router, public.router, oauth.router, pipeline.router, webhooks.router)

__all__ = ["ROUTERS"]
