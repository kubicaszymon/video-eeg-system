#!/bin/bash
set -e
#needs variables:
#ADDRESS
#USR
#PSW
#SVAROG_LOCATION

SVAROG_PKG_WIN=`ls *.exe`
SVAROG_PKG_LIN=`ls *.deb`


echo "RewriteEngine On
RewriteRule ^svarog-streamer-latest-win\.zip $SVAROG_LOCATION/svarog-streamer/$SVAROG_PKG_WIN [L,R=302]
RewriteRule ^svarog-streamer-latest-lin\.zip $SVAROG_LOCATION/svarog-streamer/$SVAROG_PKG_LIN [L,R=302]" > .htaccess

echo `git describe --tags` > version.txt

sshpass -p $PSW sftp -o StrictHostKeyChecking=no $USR@$ADDRESS << EOT
cd svarog-streamer
mput *.exe
mput *.deb
put .htaccess
put version.txt
EOT