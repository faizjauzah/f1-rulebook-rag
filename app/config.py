import os
import yaml
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    def __init__(self):
        # Load config.yaml
        with open("config.yaml", "r") as f:
            self._config = yaml.safe_load(f)
        
        # Get active profile
        self.active_profile = os.getenv("PROFILE", self._config.get("profile", "cloud"))
        
        # Get profile config
        profile_config = self._config["profiles"][self.active_profile]
        shared_config = self._config["shared"]
        
        # Embedding config
        self.embedding_provider = profile_config["embedding"]["provider"]
        self.embedding_model = profile_config["embedding"]["model"]
        
        # LLM config
        self.llm_provider = profile_config["llm"]["provider"]
        self.llm_model = profile_config["llm"]["model"]
        self.llm_temperature = profile_config["llm"]["temperature"]
        self.llm_base_url = profile_config["llm"].get("base_url")
        
        # Collection name
        self.collection_name = profile_config["collection"]
        
        # Shared config
        self.top_k = int(os.getenv("TOP_K", shared_config["top_k"]))
        self.chunk_size = int(os.getenv("CHUNK_SIZE", shared_config["chunk_size"]))
        self.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", shared_config["similarity_threshold"]))
        self.pdf_directory = os.getenv("PDF_DIRECTORY", shared_config["pdf_directory"])
        self.chroma_persist_directory = os.getenv("CHROMA_PERSIST_DIR", shared_config["chroma_persist_directory"])
        
        # API keys
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # Chroma connection (Docker)
        self.chroma_host = os.getenv("CHROMA_HOST", "localhost")
        self.chroma_port = int(os.getenv("CHROMA_PORT", "8001"))
    
    def get_profile_config(self) -> Dict[str, Any]:
        """Get the current profile configuration."""
        return self._config["profiles"][self.active_profile]
    
    def get_shared_config(self) -> Dict[str, Any]:
        """Get shared configuration."""
        return self._config["shared"]


# Global config instance
config = Config()
