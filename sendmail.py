"""
A function sending emails from kapascan@web.de.
"""

import smtplib
from email.mime.text import MIMEText
from .credentials import *

def send(to, subject, body):
    """
    Sends a text email from kapascan@web.de

    Parameters
    ----------
    to : str
        The receivers address.
    subject : str
        The subject of the message.
    body :
        The text of the message.
    """
    msg = MIMEText(body)
    msg['To'] = to
    msg['Subject'] = subject
    msg['From'] = USER

    smtp_server = smtplib.SMTP('smtp.web.de', 587)
    smtp_server.ehlo()
    smtp_server.starttls()
    smtp_server.login(USER, PASSWORD)
    smtp_server.send_message(msg)
