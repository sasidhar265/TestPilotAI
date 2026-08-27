@automation @documents
Feature: Ingest supported requirement documents safely
  As a quality engineer
  I want to upload requirement documents
  So that their normalized content can be used for test generation

  Background:
    Given the TestPilot API is available

  @FR-002
  Scenario Outline: Extract a supported requirement document
    Given a valid synthetic <file_type> requirement document
    When the client uploads it to "/api/generate/document"
    Then the response status is 200
    And the response reports a positive extracted character count
    And the extracted requirement is passed to generation and independent validation

    Examples:
      | file_type |
      | DOCX      |
      | text PDF  |
      | XLSX      |
      | PNG       |
      | JPEG      |

  @negative @FR-002 @FR-014
  Scenario Outline: Return actionable guidance for a document that cannot be read
    Given a synthetic <document_condition> requirement document
    When the client uploads it to "/api/generate/document"
    Then the request is rejected before generation
    And the error explains how the user can provide a readable supported document
    And the error does not expose document content or credentials

    Examples:
      | document_condition |
      | encrypted PDF      |
      | scanned text PDF   |
      | malformed XLSX     |
      | unsupported type   |

  @boundary @FR-003
  Scenario: Reject a file larger than 15 MB before generation
    Given a synthetic supported document larger than 15 MB
    When the client uploads it to "/api/generate/document"
    Then the request is rejected with an upload-limit error
    And no generation request is made

  @boundary @FR-003
  Scenario: Reject an image exceeding the configured pixel limit
    Given a synthetic supported image exceeding the configured pixel limit
    When the client uploads it to "/api/generate/document"
    Then the request is rejected with an image-limit error
    And no OCR or generation request is made

