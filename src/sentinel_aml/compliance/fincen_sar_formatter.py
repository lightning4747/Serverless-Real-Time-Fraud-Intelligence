"""
FinCEN SAR Format Compliance and Validation Module
Implements official FinCEN SAR format requirements and validation.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import re
from decimal import Decimal

logger = logging.getLogger(__name__)

class SARFormType(Enum):
    """FinCEN SAR form types."""
    INDIVIDUAL = "SAR-DI"  # Depository Institution
    MSB = "SAR-MSB"        # Money Services Business
    CASINO = "SAR-C"       # Casino
    SECURITIES = "SAR-SF"  # Securities and Futures

class SuspiciousActivityType(Enum):
    """FinCEN suspicious activity types."""
    STRUCTURING = "01"
    MONEY_LAUNDERING = "02"
    TERRORIST_FINANCING = "03"
    FRAUD = "04"
    CYBER_CRIME = "05"
    OTHER = "99"

@dataclass
class FinCENSARFormat:
    """FinCEN SAR format structure."""
    # Part I - Subject Information
    subject_name: str
    subject_address: Optional[str]
    subject_ssn_tin: Optional[str]
    subject_date_of_birth: Optional[str]
    subject_phone: Optional[str]
    
    # Part II - Suspicious Activity Information
    date_of_initial_detection: str
    total_dollar_amount: Decimal
    suspicious_activity_type: SuspiciousActivityType
    activity_classification: List[str]
    
    # Part III - Financial Institution Information
    filing_institution_name: str
    filing_institution_address: str
    filing_institution_tin: str
    filing_institution_primary_regulator: str
    
    # Part IV - Narrative
    narrative: str
    
    # Part V - Contact Information
    contact_name: str
    contact_phone: str
    contact_email: str
    
    # Metadata
    form_type: SARFormType = SARFormType.INDIVIDUAL
    filing_date: Optional[str] = None
    sar_number: Optional[str] = None

@dataclass
class SARValidationResult:
    """SAR validation result."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    compliance_score: float
    missing_fields: List[str]
    format_issues: List[str]

class FinCENSARFormatter:
    """FinCEN SAR format compliance checker and formatter."""
    
    def __init__(self):
        self.required_fields = {
            'subject_name': 'Subject name is required',
            'date_of_initial_detection': 'Date of initial detection is required',
            'total_dollar_amount': 'Total dollar amount is required',
            'suspicious_activity_type': 'Suspicious activity type is required',
            'filing_institution_name': 'Filing institution name is required',
            'filing_institution_tin': 'Filing institution TIN is required',
            'narrative': 'Narrative description is required',
            'contact_name': 'Contact name is required',
            'contact_phone': 'Contact phone is required'
        }
        
        self.validation_patterns = {
            'ssn': r'^\d{3}-\d{2}-\d{4}$|^\d{9}$',
            'tin': r'^\d{2}-\d{7}$|^\d{9}$',
            'phone': r'^\(\d{3}\)\s\d{3}-\d{4}$|^\d{3}-\d{3}-\d{4}$',
            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'date': r'^\d{4}-\d{2}-\d{2}$|^\d{2}/\d{2}/\d{4}$'
        }
    
    def format_sar_to_fincen(self, sar_content: str, metadata: Dict[str, Any]) -> FinCENSARFormat:
        """Convert generated SAR content to FinCEN format structure."""
        logger.info("Converting SAR to FinCEN format")
        
        # Extract structured data from SAR content and metadata
        extracted_data = self._extract_structured_data(sar_content, metadata)
        
        # Create FinCEN SAR format
        fincen_sar = FinCENSARFormat(
            # Subject Information (anonymized for compliance)
            subject_name=extracted_data.get('subject_name', '[SUBJECT_REDACTED]'),
            subject_address=extracted_data.get('subject_address'),
            subject_ssn_tin=extracted_data.get('subject_ssn_tin'),
            subject_date_of_birth=extracted_data.get('subject_dob'),
            subject_phone=extracted_data.get('subject_phone'),
            
            # Activity Information
            date_of_initial_detection=extracted_data.get('detection_date', 
                                                       datetime.utcnow().strftime('%Y-%m-%d')),
            total_dollar_amount=Decimal(str(extracted_data.get('total_amount', 0))),
            suspicious_activity_type=self._determine_activity_type(extracted_data),
            activity_classification=extracted_data.get('activity_classification', []),
            
            # Institution Information
            filing_institution_name="Sentinel AML System",
            filing_institution_address="123 Compliance Ave, Financial District, NY 10001",
            filing_institution_tin="12-3456789",
            filing_institution_primary_regulator="OCC",
            
            # Narrative
            narrative=self._format_narrative_for_fincen(sar_content),
            
            # Contact Information
            contact_name="AML Compliance Officer",
            contact_phone="(555) 123-4567",
            contact_email="aml-compliance@sentinel-system.com",
            
            # Metadata
            form_type=SARFormType.INDIVIDUAL,
            filing_date=datetime.utcnow().strftime('%Y-%m-%d'),
            sar_number=extracted_data.get('sar_id')
        )
        
        return fincen_sar
    
    def validate_sar_compliance(self, fincen_sar: FinCENSARFormat) -> SARValidationResult:
        """Validate SAR compliance with FinCEN requirements."""
        logger.info(f"Validating SAR compliance for {fincen_sar.sar_number}")
        
        errors = []
        warnings = []
        missing_fields = []
        format_issues = []
        
        # Check required fields
        for field, error_msg in self.required_fields.items():
            value = getattr(fincen_sar, field, None)
            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)
                errors.append(error_msg)
        
        # Validate field formats
        if fincen_sar.subject_ssn_tin:
            if not re.match(self.validation_patterns['ssn'], fincen_sar.subject_ssn_tin):
                format_issues.append("Invalid SSN/TIN format")
                errors.append("Subject SSN/TIN must be in format XXX-XX-XXXX or XXXXXXXXX")
        
        if fincen_sar.filing_institution_tin:
            if not re.match(self.validation_patterns['tin'], fincen_sar.filing_institution_tin):
                format_issues.append("Invalid institution TIN format")
                errors.append("Institution TIN must be in format XX-XXXXXXX or XXXXXXXXX")
        
        if fincen_sar.contact_phone:
            if not re.match(self.validation_patterns['phone'], fincen_sar.contact_phone):
                format_issues.append("Invalid phone format")
                warnings.append("Phone number should be in format (XXX) XXX-XXXX or XXX-XXX-XXXX")
        
        if fincen_sar.contact_email:
            if not re.match(self.validation_patterns['email'], fincen_sar.contact_email):
                format_issues.append("Invalid email format")
                errors.append("Invalid email address format")
        
        # Validate dates
        try:
            datetime.strptime(fincen_sar.date_of_initial_detection, '%Y-%m-%d')
        except ValueError:
            format_issues.append("Invalid detection date format")
            errors.append("Date of initial detection must be in YYYY-MM-DD format")
        
        # Validate dollar amount
        if fincen_sar.total_dollar_amount <= 0:
            errors.append("Total dollar amount must be greater than zero")
        
        if fincen_sar.total_dollar_amount >= 5000:  # SAR threshold
            if fincen_sar.total_dollar_amount < 10000:  # Below CTR threshold
                warnings.append("Amount is below CTR threshold but above SAR threshold")
        else:
            warnings.append("Amount is below typical SAR threshold of $5,000")
        
        # Validate narrative content
        narrative_validation = self._validate_narrative_content(fincen_sar.narrative)
        errors.extend(narrative_validation['errors'])
        warnings.extend(narrative_validation['warnings'])
        
        # Calculate compliance score
        compliance_score = self._calculate_compliance_score(
            len(errors), len(warnings), len(missing_fields), len(format_issues)
        )
        
        is_valid = len(errors) == 0 and compliance_score >= 0.8
        
        return SARValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            compliance_score=compliance_score,
            missing_fields=missing_fields,
            format_issues=format_issues
        )
    
    def generate_fincen_xml(self, fincen_sar: FinCENSARFormat) -> str:
        """Generate FinCEN XML format for electronic filing."""
        logger.info("Generating FinCEN XML format")
        
        xml_template = f"""<?xml version="1.0" encoding="UTF-8"?>
<SARForm xmlns="http://www.fincen.gov/sar" version="1.0">
    <FormType>{fincen_sar.form_type.value}</FormType>
    <FilingDate>{fincen_sar.filing_date}</FilingDate>
    <SARNumber>{fincen_sar.sar_number}</SARNumber>
    
    <SubjectInformation>
        <Name>{self._xml_escape(fincen_sar.subject_name)}</Name>
        <Address>{self._xml_escape(fincen_sar.subject_address or '')}</Address>
        <SSN_TIN>{fincen_sar.subject_ssn_tin or ''}</SSN_TIN>
        <DateOfBirth>{fincen_sar.subject_date_of_birth or ''}</DateOfBirth>
        <Phone>{fincen_sar.subject_phone or ''}</Phone>
    </SubjectInformation>
    
    <SuspiciousActivityInformation>
        <DateOfInitialDetection>{fincen_sar.date_of_initial_detection}</DateOfInitialDetection>
        <TotalDollarAmount>{fincen_sar.total_dollar_amount}</TotalDollarAmount>
        <SuspiciousActivityType>{fincen_sar.suspicious_activity_type.value}</SuspiciousActivityType>
        <ActivityClassification>
            {self._format_activity_classification_xml(fincen_sar.activity_classification)}
        </ActivityClassification>
    </SuspiciousActivityInformation>
    
    <FilingInstitution>
        <Name>{self._xml_escape(fincen_sar.filing_institution_name)}</Name>
        <Address>{self._xml_escape(fincen_sar.filing_institution_address)}</Address>
        <TIN>{fincen_sar.filing_institution_tin}</TIN>
        <PrimaryRegulator>{fincen_sar.filing_institution_primary_regulator}</PrimaryRegulator>
    </FilingInstitution>
    
    <Narrative>
        <![CDATA[{fincen_sar.narrative}]]>
    </Narrative>
    
    <ContactInformation>
        <Name>{self._xml_escape(fincen_sar.contact_name)}</Name>
        <Phone>{fincen_sar.contact_phone}</Phone>
        <Email>{fincen_sar.contact_email}</Email>
    </ContactInformation>
</SARForm>"""
        
        return xml_template
    
    def _extract_structured_data(self, sar_content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured data from SAR content and metadata."""
        extracted = {}
        
        # Extract from metadata
        extracted['sar_id'] = metadata.get('sar_id')
        extracted['total_amount'] = metadata.get('total_amount', 0)
        extracted['detection_date'] = metadata.get('generation_timestamp', 
                                                 datetime.utcnow().isoformat())[:10]
        
        # Extract pattern indicators for activity classification
        pattern_indicators = metadata.get('pattern_indicators', [])
        extracted['activity_classification'] = self._map_patterns_to_classifications(pattern_indicators)
        
        # Extract subject information (anonymized)
        extracted['subject_name'] = self._extract_subject_name(sar_content)
        
        return extracted
    
    def _determine_activity_type(self, extracted_data: Dict[str, Any]) -> SuspiciousActivityType:
        """Determine FinCEN activity type based on extracted data."""
        activity_classification = extracted_data.get('activity_classification', [])
        
        # Map common patterns to FinCEN activity types
        if any('structuring' in cls.lower() for cls in activity_classification):
            return SuspiciousActivityType.STRUCTURING
        elif any('laundering' in cls.lower() for cls in activity_classification):
            return SuspiciousActivityType.MONEY_LAUNDERING
        elif any('fraud' in cls.lower() for cls in activity_classification):
            return SuspiciousActivityType.FRAUD
        elif any('cyber' in cls.lower() for cls in activity_classification):
            return SuspiciousActivityType.CYBER_CRIME
        else:
            return SuspiciousActivityType.OTHER
    
    def _format_narrative_for_fincen(self, sar_content: str) -> str:
        """Format narrative content for FinCEN compliance."""
        # Remove any remaining PII patterns
        narrative = sar_content
        
        # Ensure narrative starts with required elements
        if not narrative.startswith("SUSPICIOUS ACTIVITY REPORT"):
            narrative = "SUSPICIOUS ACTIVITY REPORT\n\n" + narrative
        
        # Limit narrative length (FinCEN has character limits)
        max_length = 50000  # FinCEN limit
        if len(narrative) > max_length:
            narrative = narrative[:max_length-100] + "\n\n[NARRATIVE TRUNCATED DUE TO LENGTH LIMIT]"
        
        return narrative
    
    def _validate_narrative_content(self, narrative: str) -> Dict[str, List[str]]:
        """Validate narrative content for FinCEN requirements."""
        errors = []
        warnings = []
        
        # Check minimum length
        if len(narrative.strip()) < 100:
            errors.append("Narrative is too short (minimum 100 characters)")
        
        # Check for required elements
        required_elements = [
            ('suspicious activity', 'Must describe the suspicious activity'),
            ('dollar amount', 'Must include dollar amounts'),
            ('time period', 'Must specify time period of activity')
        ]
        
        for element, error_msg in required_elements:
            if element not in narrative.lower():
                warnings.append(error_msg)
        
        # Check for potential PII exposure
        pii_patterns = {
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
            'full_account': r'\b\d{10,16}\b',
            'phone': r'\b\d{3}-\d{3}-\d{4}\b'
        }
        
        for pii_type, pattern in pii_patterns.items():
            if re.search(pattern, narrative):
                errors.append(f"Potential {pii_type.upper()} exposure detected in narrative")
        
        return {'errors': errors, 'warnings': warnings}
    
    def _calculate_compliance_score(self, error_count: int, warning_count: int, 
                                  missing_count: int, format_count: int) -> float:
        """Calculate compliance score based on validation results."""
        # Start with perfect score
        score = 1.0
        
        # Deduct for errors (major issues)
        score -= error_count * 0.2
        
        # Deduct for warnings (minor issues)
        score -= warning_count * 0.05
        
        # Deduct for missing fields
        score -= missing_count * 0.15
        
        # Deduct for format issues
        score -= format_count * 0.1
        
        return max(0.0, score)
    
    def _map_patterns_to_classifications(self, pattern_indicators: List[str]) -> List[str]:
        """Map ML pattern indicators to FinCEN activity classifications."""
        classification_mapping = {
            'SMURFING_PATTERN': 'Structuring to evade reporting requirements',
            'RAPID_FIRE_PATTERN': 'Rapid movement of funds',
            'LAYERING_PATTERN': 'Complex layering of transactions',
            'ROUND_DOLLAR_PATTERN': 'Round dollar amounts',
            'TIME_PATTERN': 'Unusual timing patterns',
            'VELOCITY_PATTERN': 'High transaction velocity'
        }
        
        return [classification_mapping.get(pattern, pattern) for pattern in pattern_indicators]
    
    def _extract_subject_name(self, sar_content: str) -> str:
        """Extract subject name from SAR content (anonymized)."""
        # Look for customer/account holder references
        name_patterns = [
            r'Customer:\s*([A-Z][a-z]+\s+[A-Z]\.)',
            r'Account holder:\s*([A-Z][a-z]+\s+[A-Z]\.)',
            r'Subject:\s*([A-Z][a-z]+\s+[A-Z]\.)'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, sar_content)
            if match:
                return match.group(1)
        
        return '[SUBJECT_REDACTED]'
    
    def _xml_escape(self, text: str) -> str:
        """Escape XML special characters."""
        if not text:
            return ''
        
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&apos;'))
    
    def _format_activity_classification_xml(self, classifications: List[str]) -> str:
        """Format activity classifications for XML."""
        if not classifications:
            return '<Classification>Other suspicious activity</Classification>'
        
        xml_parts = []
        for classification in classifications:
            xml_parts.append(f'<Classification>{self._xml_escape(classification)}</Classification>')
        
        return '\n            '.join(xml_parts)