# ABAPCleaner_Auto

Der Standalone ABAP Cleaner muss installiert werden und der entsprechende Pfad am Anfang entsprechend aktualisiert werden.

Vorm ausführen des Programms müssen Login Daten als Umgebungsvariabeln gesetzt werden:
$env:SAP_USER = "USER"
$env:SAP_PASS = "PASSWORD"

Zum Ausführen des Programms:

Programm Argumente
--base        Basis-URL des SAP ABAP ADT-Endpunkts
--client      SAP-Mandant, in dem das Programm ausgeführt wird
--insecure    Deaktiviert die SSL-Zertifikatsprüfung (z. B. bei Self-Signed-Zertifikaten)
--mode        test (Testlauf, Ergebnisse werden nur als Txt gespeichert), writeback (Ergebnisse werden ins SAP System geschrieben und aktiviert)
--corrnr      Transportauftrag (Korrektur-/Transportnummer), in den Änderungen geschrieben werden
--urls-file   Textdatei mit einer Liste von ADT-URLs, die verarbeitet werden sollen

Beispiel für Zirrus Intern:
python script_writeback.py `
  --base "https://ip:port/sap/bc/adt" `
  --client 001 `
  --insecure `
  --mode test `
  --corrnr A4HK900118 `
  --urls-file urls.txt

Die entsprechende URLs werden in einer txt-Datei zeilenweise hinterlegt.

Nach Ausführen des Programms werden im Output Ordner Fehler bzw. Ergebnisse des Testmodus angezeigt.
