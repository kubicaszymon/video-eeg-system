#!/bin/bash

pip3 install -U pip==18.0
pip3 install -r apps/win_build_requirements.txt
pip3 install -r apps/mac_requirements.txt
mkdir -p dist
cd apps || exit
pyinstaller brain.spec

cp -r dist/brain/PySide2/Qt/lib/QtWebEngineCore.framework/Resources/* dist/brain/

curl -L https://obci:dlugi_przedluzacz@obci-stable.braintech.pl/oferta_na_strone/artifacts/svarog-2.5.6-97-g00cb09c-standalone.zip --output svarog.zip
unzip svarog.zip -d svarog

curl -L https://obci:dlugi_przedluzacz@obci-stable.braintech.pl/oferta_na_strone/artifacts/zulu8.40.0.25-ca-fx-jre8.0.222-macosx_x64.zip --output jre.zip
unzip jre.zip -d jre
mv jre/zulu* dist/jre

mv svarog/svarog* dist/svarog

mv dist ../dist/svarog_streamer_mac
cd ../dist || exit

mkdir svarog_streamer_mac.app
mkdir svarog_streamer_mac.app/Contents
mkdir svarog_streamer_mac.app/Contents/MacOS
mkdir svarog_streamer_mac.app/Contents/Resources

mv svarog_streamer_mac/* svarog_streamer_mac.app/Contents/MacOS
cp ../resources/Info.plist svarog_streamer_mac.app/Contents



sips -z 256 256 ../svarog_streamer/resources/braintech.png --out myIconResized.png
sips -s format icns myIconResized.png --out svarog_streamer_mac.app/Contents/Resources/braintech.icns
