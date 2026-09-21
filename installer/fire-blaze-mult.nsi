Unicode true
!include "MUI2.nsh"

!define APP_NAME "FIRE BLAZE Mult"
!define APP_VERSION "1.0.1"
!define COMPANY "FIRE BLAZE"
!define EXE_NAME "FIRE BLAZE Mult.exe"
!define INSTALL_DIR "$LOCALAPPDATA\\Programs\\FIRE BLAZE Mult"

Name "${APP_NAME}"
OutFile "FIRE-BLAZE-Mult-Setup.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "FIRE BLAZE Mult"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bem-vindo ao FIRE BLAZE Mult"
!define MUI_WELCOMEPAGE_TEXT "Este assistente instalará o FIRE BLAZE Mult ${APP_VERSION} no seu computador.$\r$\n$\r$\nSe uma versão anterior estiver instalada, ela será atualizada."
!define MUI_FINISHPAGE_RUN "$INSTDIR\\${EXE_NAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir FIRE BLAZE Mult"
!define MUI_FINISHPAGE_LINK "FIRE BLAZE Mult"
!define MUI_FINISHPAGE_LINK_LOCATION "https://fire-blaze-mult-site.onrender.com"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "FIRE BLAZE Mult" SEC01
  SetOutPath "$INSTDIR"
  File /r "payload\\*.*"
  WriteUninstaller "$INSTDIR\\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\\FIRE BLAZE Mult"
  CreateShortcut "$SMPROGRAMS\\FIRE BLAZE Mult\\FIRE BLAZE Mult.lnk" "$INSTDIR\\${EXE_NAME}" "" "$INSTDIR\\resources\\app\\assets\\fire-blaze.ico" 0
  CreateShortcut "$DESKTOP\\FIRE BLAZE Mult.lnk" "$INSTDIR\\${EXE_NAME}" "" "$INSTDIR\\resources\\app\\assets\\fire-blaze.ico" 0

  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "Publisher" "${COMPANY}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "NoModify" 1
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\\FIRE BLAZE Mult.lnk"
  Delete "$SMPROGRAMS\\FIRE BLAZE Mult\\FIRE BLAZE Mult.lnk"
  RMDir "$SMPROGRAMS\\FIRE BLAZE Mult"
  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FIRE BLAZE Mult"
  RMDir /r "$INSTDIR"
SectionEnd
