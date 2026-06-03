############################################################################################
#      NSIS Installation Script created by NSIS Quick Setup Script Generator v1.09.18
#               Entirely Edited with NullSoft Scriptable Installation System
#              by Vlasis K. Barkas aka Red Wine red_wine@freemail.gr Sep 2006
############################################################################################

!define APP_NAME "Svarog Streamer"
!define COMP_NAME "Braintech LTD"
!define WEB_SITE "www.braintech.pl"
!define VERSION "__NSISVERSION__"
!define FULLVERSION "__VERSION__"
!define COPYRIGHT "Braintech 2020"
!define DESCRIPTION "Svarog Streamer version: __VERSION__"
!define INSTALLER_NAME "Svarog_Streamer_install_v__VERSION__.exe"
!define MAIN_APP_EXE "svarog_streamer.exe"
!define INSTALL_TYPE "SetShellVarContext all"
!define REG_ROOT "HKLM"
!define REG_APP_PATH "Software\Microsoft\Windows\CurrentVersion\App Paths\${MAIN_APP_EXE}"
!define UNINSTALL_PATH "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"


######################################################################

VIProductVersion  "${VERSION}"
VIAddVersionKey "ProductName"  "${APP_NAME}"
VIAddVersionKey "CompanyName"  "${COMP_NAME}"
VIAddVersionKey "LegalCopyright"  "${COPYRIGHT}"
VIAddVersionKey "FileDescription"  "${DESCRIPTION}"
VIAddVersionKey "FileVersion"  "${VERSION}"

######################################################################

SetCompressor /solid ZLIB
Name "${APP_NAME}"
Caption "${APP_NAME}"
OutFile "${INSTALLER_NAME}"
BrandingText "${APP_NAME}"
XPStyle on
InstallDirRegKey "${REG_ROOT}" "${REG_APP_PATH}" ""
InstallDir "$PROGRAMFILES\Svarog Streamer"

######################################################################

!include "MUI.nsh"

!define MUI_ICON apps\braintech.ico
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "resources\installer_art\header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "resources\installer_art\welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "resources\installer_art\welcome.bmp"


!define MUI_ABORTWARNING
!define MUI_UNABORTWARNING

!insertmacro MUI_PAGE_WELCOME

!ifdef LICENSE_TXT
!insertmacro MUI_PAGE_LICENSE "${LICENSE_TXT}"
!endif

!insertmacro MUI_PAGE_DIRECTORY

!ifdef REG_START_MENU
!define MUI_STARTMENUPAGE_NODISABLE
!define MUI_STARTMENUPAGE_DEFAULTFOLDER "Svarog Streamer"
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "${REG_ROOT}"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "${UNINSTALL_PATH}"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "${REG_START_MENU}"
!insertmacro MUI_PAGE_STARTMENU Application $SM_Folder
!endif

!insertmacro MUI_PAGE_INSTFILES

!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM

!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

######################################################################

; The "" makes the section hidden.
Section -SecUninstallPrevious

    Call UninstallPrevious

SectionEnd

Function UninstallPrevious

    ; Check for uninstaller.
    ReadRegStr $R0 HKLM "${UNINSTALL_PATH}" "UninstallString"
    DetailPrint "Uninstaller path $R0"
    ${If} $R0 == ""
        Goto Done
    ${EndIf}

    DetailPrint "Removing previous installation."

    MessageBox MB_YESNO "Uninstall previous version?" IDYES true IDNO false
    true:
      ExecWait '"$R0" /S _?=$INSTDIR'
      Goto Done
    false:
      Abort
    ; Run the uninstaller silently.
    Done:

FunctionEnd

Section -MainProgram
${INSTALL_TYPE}
SetOverwrite ifnewer
SetOutPath "$INSTDIR"
File /r ".\dist\"

FileOpen $9 "$INSTDIR\version.txt" w ;Opens a Empty File and fills it
FileWrite $9 "${APP_NAME}:${FULLVERSION}"
FileClose $9 ;Closes the filled file
SectionEnd

######################################################################

; These are the programs that are needed by Svarog Streamer
Section -Prerequisites
  SetOutPath $INSTDIR\redist
    File ".\dist\svarog_streamer\redist\InstallPerun32Driver.exe"
    ExecWait "$INSTDIR\redist\InstallPerun32Driver.exe /S"
    ExecWait "$INSTDIR\svarog_streamer\svarog_streamer.exe init"
SectionEnd

Section -Icons_Reg
SetOutPath "$INSTDIR"
WriteUninstaller "$INSTDIR\uninstall.exe"

SetOutPath "$INSTDIR\svarog_streamer"
!ifdef REG_START_MENU
!insertmacro MUI_STARTMENU_WRITE_BEGIN Application
CreateDirectory "$SMPROGRAMS\Svarog Streamer"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\${APP_NAME}.lnk" "$INSTDIR\svarog_streamer\${MAIN_APP_EXE}" "svarog" "$INSTDIR\svarog_streamer\svarog.ico"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\${APP_NAME} P300 Demo.lnk" "$INSTDIR\svarog_streamer\${MAIN_APP_EXE}" "p300" "$INSTDIR\svarog_streamer\braintech.ico"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\Perun amplifier LSL Streaming app.lnk" "cmd.exe" "/K cd /d $INSTDIR\svarog_streamer\ & echo running svarog_streamer.exe -h & svarog_streamer.exe -h"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\Uninstall ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe"

!ifdef WEB_SITE
WriteIniStr "$INSTDIR\${APP_NAME} website.url" "InternetShortcut" "URL" "${WEB_SITE}"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\${APP_NAME} Website.lnk" "$INSTDIR\${APP_NAME} website.url" "" "$INSTDIR\svarog_streamer\braintech.ico"
!endif
!insertmacro MUI_STARTMENU_WRITE_END
!endif

!ifndef REG_START_MENU
CreateDirectory "$SMPROGRAMS\Svarog Streamer"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\${APP_NAME}.lnk" "$INSTDIR\svarog_streamer\${MAIN_APP_EXE}" "svarog" "$INSTDIR\svarog_streamer\svarog.ico"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\${APP_NAME} P300 Demo.lnk" "$INSTDIR\svarog_streamer\${MAIN_APP_EXE}" "p300" "$INSTDIR\svarog_streamer\braintech.ico"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\Perun amplifier LSL Streaming app.lnk" "cmd.exe" "/K cd /d $INSTDIR\svarog_streamer\ & echo running svarog_streamer.exe -h & svarog_streamer.exe -h"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\Uninstall ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe"

!ifdef WEB_SITE
WriteIniStr "$INSTDIR\${APP_NAME} website.url" "InternetShortcut" "URL" "${WEB_SITE}"
CreateShortCut "$SMPROGRAMS\Svarog Streamer\${APP_NAME} Website.lnk" "$INSTDIR\${APP_NAME} website.url" "" "$INSTDIR\svarog_streamer\braintech.ico"
!endif
!endif

WriteRegStr ${REG_ROOT} "${REG_APP_PATH}" "" "$INSTDIR\${MAIN_APP_EXE}"
WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}"  "DisplayName" "${APP_NAME}"
WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}"  "UninstallString" "$INSTDIR\uninstall.exe"
WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}"  "DisplayIcon" "$INSTDIR\${MAIN_APP_EXE}"
WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}"  "DisplayVersion" "${VERSION}"
WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}"  "Publisher" "${COMP_NAME}"

!ifdef WEB_SITE
WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}"  "URLInfoAbout" "${WEB_SITE}"
!endif
SectionEnd

######################################################################

Section Uninstall
${INSTALL_TYPE}

Delete "$INSTDIR\uninstall.exe"
!ifdef WEB_SITE
Delete "$INSTDIR\${APP_NAME} website.url"
!endif

RmDir /r "$INSTDIR"

!ifdef REG_START_MENU
!insertmacro MUI_STARTMENU_GETFOLDER "Application" $SM_Folder
Delete "$SMPROGRAMS\Svarog Streamer\${APP_NAME}.lnk"
Delete "$SMPROGRAMS\Svarog Streamer\${APP_NAME} P300 Demo.lnk"
Delete "$SMPROGRAMS\Svarog Streamer\Perun amplifier LSL Streaming app.lnk"
Delete "$SMPROGRAMS\Svarog Streamer\Uninstall ${APP_NAME}.lnk"
!ifdef WEB_SITE
Delete "$SMPROGRAMS\Svarog Streamer\${APP_NAME} Website.lnk"
!endif
RmDir "$SMPROGRAMS\Svarog Streamer"
!endif

!ifndef REG_START_MENU
Delete "$SMPROGRAMS\Svarog Streamer\${APP_NAME}.lnk"
Delete "$SMPROGRAMS\Svarog Streamer\${APP_NAME} P300 Demo.lnk"
Delete "$SMPROGRAMS\Svarog Streamer\Uninstall ${APP_NAME}.lnk"
Delete "$SMPROGRAMS\Svarog Streamer\Perun amplifier LSL Streaming app.lnk"
!ifdef WEB_SITE
Delete "$SMPROGRAMS\Svarog Streamer\${APP_NAME} Website.lnk"
!endif
RmDir "$SMPROGRAMS\Svarog Streamer"
!endif

DeleteRegKey ${REG_ROOT} "${REG_APP_PATH}"
DeleteRegKey ${REG_ROOT} "${UNINSTALL_PATH}"
SectionEnd

######################################################################

