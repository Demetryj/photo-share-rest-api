from enum import Enum


class HTTPStatusMessages(Enum):
    successfully_created = "Successfully created"
    successful_email_verification = "Successful email verification"
    account_already_exists = "Account already exists"

    invalid_token_for_email_verification = "Invalid token for email verification"
    verification_error = "Verification error"


class EmailMessages(Enum):
    email_confirmed = "Email confirmed"
    email_already_confirmed = "Your email is already confirmed."
