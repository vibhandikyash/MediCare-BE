"""Supabase database connection and configuration."""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Global Supabase client
_supabase_client = None

def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    global _supabase_client
    
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        
        # Strip whitespace
        supabase_url = supabase_url.strip()
        supabase_key = supabase_key.strip()
        
        # Add https:// if missing
        if not supabase_url.startswith(("http://", "https://")):
            supabase_url = f"https://{supabase_url}"
        
        _supabase_client = create_client(supabase_url, supabase_key)
    
    return _supabase_client
