from enum import Enum


class HTTPStatusMessages(Enum):
    success = "Success"
    successfully_created = "Successfully created"
    successful_email_verification = "Successful email verification"
    account_already_exists = "Account already exists"

    invalid_token_for_email_verification = "Invalid token for email verification"
    verification_error = "Verification error"
    invalid_email_or_password = "Invalid email or password"
    email_not_confirmed = "Email not confirmed"


class EmailMessages(Enum):
    email_confirmed = "Email confirmed"
    email_already_confirmed = "Your email is already confirmed."
