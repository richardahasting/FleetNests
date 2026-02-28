#!/bin/bash
set -e
echo "!QAZ2wsx#EDC" | sudo -S mkdir -p /etc/opendkim/keys/fleetnests.com
echo "!QAZ2wsx#EDC" | sudo -S opendkim-genkey -b 2048 -d fleetnests.com -D /etc/opendkim/keys/fleetnests.com -s mail -v
echo "!QAZ2wsx#EDC" | sudo -S chown -R opendkim:opendkim /etc/opendkim/keys/fleetnests.com
echo "!QAZ2wsx#EDC" | sudo -S chmod 600 /etc/opendkim/keys/fleetnests.com/mail.private
echo "--- Public key DNS record ---"
echo "!QAZ2wsx#EDC" | sudo -S cat /etc/opendkim/keys/fleetnests.com/mail.txt
touch /home/richard/projects/fleetnests/runme-dkim.complete
