#!/bin/bash
set -e
echo "!QAZ2wsx#EDC" | sudo -S mkdir -p /etc/opendkim/keys/bentleyboatclub.com
echo "!QAZ2wsx#EDC" | sudo -S opendkim-genkey -b 2048 -d bentleyboatclub.com -D /etc/opendkim/keys/bentleyboatclub.com -s mail -v
echo "!QAZ2wsx#EDC" | sudo -S chown -R opendkim:opendkim /etc/opendkim/keys/bentleyboatclub.com
echo "!QAZ2wsx#EDC" | sudo -S chmod 600 /etc/opendkim/keys/bentleyboatclub.com/mail.private
echo "--- Public key DNS record ---"
echo "!QAZ2wsx#EDC" | sudo -S cat /etc/opendkim/keys/bentleyboatclub.com/mail.txt
touch /home/richard/projects/bentley-boat/runme-dkim.complete
