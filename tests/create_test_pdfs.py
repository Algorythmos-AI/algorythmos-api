"""Script to create test PDF fixtures."""

import io

# Create a minimal valid PDF content using raw PDF format
minimal_pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test PDF document) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000109 00000 n 
0000000176 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
268
%%EOF"""

# Write valid test PDF
with open('/Users/skalaliya/Desktop/api-algorythmos/tests/data/valid_test.pdf', 'wb') as f:
    f.write(minimal_pdf_content)

# Create a corrupt PDF (invalid header)
corrupt_pdf_content = b"Not a real PDF file content"
with open('/Users/skalaliya/Desktop/api-algorythmos/tests/data/corrupt_test.pdf', 'wb') as f:
    f.write(corrupt_pdf_content)

print("Created test PDF fixtures")