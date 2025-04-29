from urllib.parse import parse_qs

class Query:
    """Class to handle query string parameters for OEmbed requests."""
    
    def __init__(self, qs):
        """Initialize with a query string."""
        self.query_string = qs
        self.params = {}
        
        if qs:
            # Parse the query string into a dictionary
            parsed = parse_qs(qs)
            # Convert lists to single values for easier access
            self.params = {k: v[0] if v and len(v) == 1 else v for k, v in parsed.items()}
    
    def __bool__(self):
        """Return True if there are parameters."""
        return bool(self.params)
    
    def __str__(self):
        """Convert back to query string for URL construction."""
        return self.query_string