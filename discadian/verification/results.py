class VerificationResult:
    def __init__(self, success: bool, message: str, nation: str = None, town: str = None, 
                 contradiction_data: str = None, is_mayor: bool = False, county: str = None, 
                 has_county: bool = True):
        self.success = success
        self.message = message
        self.nation = nation
        self.town = town
        self.contradiction_data = contradiction_data
        self.is_mayor = is_mayor
        self.county = county
        self.has_county = has_county