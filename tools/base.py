class Tool:
    name: str = ""
    description: str = ""

    def run(self, **kwargs):
        
        raise NotImplementedError("Tool must implement run()")
