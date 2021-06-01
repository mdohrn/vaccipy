#!/usr/bin/env python3

import argparse
import copy
import json
import os
import random
import string

try:
    import readline
except:
    pass

from tools.its import ImpfterminService
from tools.kontaktdaten import get_kontaktdaten, validate_kontaktdaten
from tools.utils import create_missing_dirs, remove_prefix
from tools.exceptions import ValidationError

PATH = os.path.dirname(os.path.realpath(__file__))


def update_kontaktdaten_interactive(
        known_kontaktdaten,
        command,
        filepath=None):
    """
    Interaktive Eingabe und anschließendes Abspeichern der Kontaktdaten.

    :param known_kontaktdaten: Bereits bekannte Kontaktdaten, die nicht mehr
        abgefragt werden sollen.
    :param command: Entweder "code" oder "search". Bestimmt, welche
        Kontaktdaten überhaupt benötigt werden.
    :param filepath: Pfad zur JSON-Datei zum Abspeichern der Kontaktdaten.
        Default: data/kontaktdaten.json im aktuellen Ordner
    :return: Dictionary mit Kontaktdaten
    """

    assert (command in ["code", "search"])

    # Werfe Fehler, falls die übergebenen Kontaktdaten bereits ungültig sind.
    validate_kontaktdaten(known_kontaktdaten)

    kontaktdaten = copy.deepcopy(known_kontaktdaten)

    with open(filepath, 'w', encoding='utf-8') as file:
        if "plz_impfzentren" not in kontaktdaten:
            print(
                "Mit einem Code kann in mehreren Impfzentren gleichzeitig nach einem Termin gesucht werden.\n"
                "Eine Übersicht über die Gruppierung der Impfzentren findest du hier:\n"
                "https://github.com/iamnotturner/vaccipy/wiki/Ein-Code-fuer-mehrere-Impfzentren\n\n"
                "Trage nun die PLZ deines Impfzentrums ein. Für mehrere Impfzentren die PLZ's kommagetrennt nacheinander.\n"
                "Beispiel: 68163, 69124, 69469\n")
            input_kontaktdaten_key(kontaktdaten,
                                   ["plz_impfzentren"],
                                   "> PLZ's der Impfzentren: ",
                                   lambda x: list(set([plz.strip() for plz in x.split(",")])))

        if "code" not in kontaktdaten and command == "search":
            input_kontaktdaten_key(kontaktdaten, ["code"], "> Code: ")

        if "kontakt" not in kontaktdaten:
            kontaktdaten["kontakt"] = {}

        if "anrede" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "anrede"], "> Anrede (Frau/Herr/...): ")

        if "vorname" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "vorname"], "> Vorname: ")

        if "nachname" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "nachname"], "> Nachname: ")

        if "strasse" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "strasse"], "> Strasse (ohne Hausnummer): ")

        if "hausnummer" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "hausnummer"], "> Hausnummer: ")

        if "plz" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "plz"], "> PLZ des Wohnorts: ")

        if "ort" not in kontaktdaten["kontakt"] and command == "search":
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "ort"], "> Wohnort: ")

        if "phone" not in kontaktdaten["kontakt"]:
            input_kontaktdaten_key(
                kontaktdaten,
                ["kontakt", "phone"],
                "> Telefonnummer: +49",
                lambda x: x if x.startswith("+49") else f"+49{remove_prefix(x, '0')}")

        if "notificationChannel" not in kontaktdaten["kontakt"]:
            kontaktdaten["kontakt"]["notificationChannel"] = "email"

        if "notificationReceiver" not in kontaktdaten["kontakt"]:
            input_kontaktdaten_key(
                kontaktdaten, ["kontakt", "notificationReceiver"], "> Mail: ")

        json.dump(kontaktdaten, file, ensure_ascii=False, indent=4)

    return kontaktdaten


def input_kontaktdaten_key(
        kontaktdaten,
        path,
        prompt,
        transformer=lambda x: x):
    target = kontaktdaten
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    while True:
        target[key] = transformer(input(prompt).strip())
        try:
            validate_kontaktdaten(kontaktdaten)
            break
        except ValidationError as exc:
            print(f"\n{str(exc)}\n")


def run_search_interactive(kontaktdaten_path, check_delay):
    """
    Interaktives Setup für die Terminsuche:
    1. Ggf. zuerst Eingabe, ob Kontaktdaten aus kontaktdaten.json geladen
       werden sollen.
    2. Laden der Kontaktdaten aus kontaktdaten.json.
    3. Bei unvollständigen Kontaktdaten: Interaktive Eingabe der fehlenden
       Kontaktdaten.
    4. Terminsuche

    :param kontaktdaten_path: Pfad zur JSON-Datei mit Kontaktdaten. Default: data/kontaktdaten.json im aktuellen Ordner
    """

    print(
        "Bitte trage zunächst deinen Impfcode und deine Kontaktdaten ein.\n"
        f"Die Daten werden anschließend lokal in der Datei '{os.path.basename(kontaktdaten_path)}' abgelegt.\n"
        "Du musst sie zukünftig nicht mehr eintragen.\n")

    kontaktdaten = {}
    if os.path.isfile(kontaktdaten_path):
        daten_laden = input(
            f"> Sollen die vorhandenen Daten aus '{os.path.basename(kontaktdaten_path)}' geladen werden (y/n)?: ").lower()
        if daten_laden.lower() != "n":
            kontaktdaten = get_kontaktdaten(kontaktdaten_path)

    print()
    kontaktdaten = update_kontaktdaten_interactive(
        kontaktdaten, "search", kontaktdaten_path)
    return run_search(kontaktdaten, check_delay)


def run_search(kontaktdaten, check_delay):
    """
    Nicht-interaktive Terminsuche

    :param kontaktdaten: Dictionary mit Kontaktdaten
    """

    try:
        code = kontaktdaten["code"]

        # Hinweis, wenn noch alte Version der Kontaktdaten.json verwendet wird
        if kontaktdaten.get("plz"):
            print(
                "ACHTUNG: Du verwendest noch die alte Version der 'Kontaktdaten.json'!\n"
                "Lösche vor dem nächsten Ausführen die Datei und fülle die Kontaktdaten bitte erneut aus.\n")
            plz_impfzentren = [kontaktdaten.get("plz")]
        else:
            plz_impfzentren = kontaktdaten["plz_impfzentren"]

        kontakt = kontaktdaten["kontakt"]
        print(
            f"Kontaktdaten wurden geladen für: {kontakt['vorname']} {kontakt['nachname']}\n")
    except KeyError as exc:
        raise ValueError(
            "Kontaktdaten konnten nicht aus 'kontaktdaten.json' geladen werden.\n"
            "Bitte überprüfe, ob sie im korrekten JSON-Format sind oder gebe "
            "deine Daten beim Programmstart erneut ein.\n") from exc

    ImpfterminService.terminsuche(code=code, plz_impfzentren=plz_impfzentren, kontakt=kontakt,
                                  check_delay=check_delay, PATH=PATH)


def gen_code_interactive(kontaktdaten_path):
    """
    Interaktives Setup für die Codegenerierung:
    1. Ggf. zuerst Eingabe, ob Kontaktdaten aus kontaktdaten.json geladen
       werden sollen.
    2. Laden der Kontaktdaten aus kontaktdaten.json.
    3. Bei unvollständigen Kontaktdaten: Interaktive Eingabe derjenigen
       fehlenden Kontaktdaten, die für die Codegenerierung benötigt werden.
    4. Codegenerierung

    :param kontaktdaten_path: Pfad zur JSON-Datei mit Kontaktdaten. Default: kontaktdaten.json im aktuellen Ordner
    """

    print(
        "Du kannst dir jetzt direkt einen Impf-Code erstellen.\n"
        "Dazu benötigst du eine Mailadresse, Telefonnummer und die PLZ deines Impfzentrums.\n"
        f"Die Daten werden anschließend lokal in der Datei '{os.path.basename(kontaktdaten_path)}' abgelegt.\n"
        "Du musst sie zukünftig nicht mehr eintragen.\n")

    kontaktdaten = {}
    if os.path.isfile(kontaktdaten_path):
        daten_laden = input(
            f"> Sollen die vorhandenen Daten aus '{os.path.basename(kontaktdaten_path)}' geladen werden (y/n)?: ").lower()
        if daten_laden.lower() != "n":
            kontaktdaten = get_kontaktdaten(kontaktdaten_path)

    print()
    kontaktdaten = update_kontaktdaten_interactive(
        kontaktdaten, "code", kontaktdaten_path)
    return gen_code(kontaktdaten)


def gen_code(kontaktdaten):
    """
    Codegenerierung ohne interaktive Eingabe der Kontaktdaten

    :param kontaktdaten: Dictionary mit Kontaktdaten
    """

    try:
        plz_impfzentrum = kontaktdaten["plz_impfzentren"][0]
        mail = kontaktdaten["kontakt"]["notificationReceiver"]
        telefonnummer = kontaktdaten["kontakt"]["phone"]
        if not telefonnummer.startswith("+49"):
            telefonnummer = f"+49{remove_prefix(telefonnummer, '0')}"
    except KeyError as exc:
        raise ValueError(
            "Kontaktdaten konnten nicht aus 'kontaktdaten.json' geladen werden.\n"
            "Bitte überprüfe, ob sie im korrekten JSON-Format sind oder gebe "
            "deine Daten beim Programmstart erneut ein.\n") from exc

    # Erstelle Zufallscode nach Format XXXX-YYYY-ZZZZ
    # für die Cookie-Generierung
    code_chars = string.ascii_uppercase + string.digits
    one = 'VACC'
    two = 'IPY' + random.choice(code_chars)
    three = ''.join(random.choices(code_chars, k=4))
    random_code = f"{one}-{two}-{three}"
    print(f"Für die Cookies-Generierung wird ein zufälliger Code verwendet ({random_code}).\n")

    its = ImpfterminService(random_code, [plz_impfzentrum], {}, PATH)

    print("Wähle nachfolgend deine Altersgruppe aus (L920, L921, L922 oder L923).\n"
          "Es ist wichtig, dass du die Gruppe entsprechend deines Alters wählst, "
          "ansonsten wird dir der Termin vor Ort abgesagt.\n"
          "In den eckigen Klammern siehst du, welche Impfstoffe den Gruppe jeweils zugeordnet sind.\n"
          "Beispiel: L921\n")

    while True:
        leistungsmerkmal = input("> Leistungsmerkmal: ").upper()
        if leistungsmerkmal in ["L920", "L921", "L922", "L923"]:
            break
        print("Falscheingabe! Bitte erneut versuchen:")

    # cookies erneuern und code anfordern
    its.renew_cookies_code()
    token = its.code_anfordern(mail, telefonnummer, plz_impfzentrum, leistungsmerkmal)

    if token is not None:
        # code bestätigen
        print("\nDu erhältst gleich eine SMS mit einem Code zur Bestätigung deiner Telefonnummer.\n"
              "Trage diesen hier ein. Solltest du dich vertippen, hast du noch 2 weitere Versuche.\n"
              "Beispiel: 123-456\n")

        # 3 Versuche für die SMS-Code-Eingabe
        for _ in range(3):
            sms_pin = input("> SMS-Code: ").replace("-", "")
            if its.code_bestaetigen(token, sms_pin):
                print("\nDu kannst jetzt mit der Terminsuche fortfahren.\n")
                return True

    print("\nDie Code-Generierung war leider nicht erfolgreich.\n")
    return False


def subcommand_search(args):
    if args.configure_only:
        update_kontaktdaten_interactive(
            get_kontaktdaten(args.file), "search", args.file)
    elif args.read_only:
        run_search(get_kontaktdaten(args.file), check_delay=args.retry_sec)
    else:
        run_search_interactive(args.file, check_delay=args.retry_sec)


def subcommand_code(args):
    if args.configure_only:
        update_kontaktdaten_interactive(
            get_kontaktdaten(args.file), "code", args.file)
    elif args.read_only:
        gen_code(get_kontaktdaten(args.file))
    else:
        gen_code_interactive(args.file)


def validate_args(args):
    """
    Raises ValueError if args contain invalid settings.
    """

    if args.configure_only and args.read_only:
        raise ValueError(
            "--configure-only und --read-only kann nicht gleichzeitig verwendet werden")


def main():
    create_missing_dirs()

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="commands", dest="command")

    base_subparser = argparse.ArgumentParser(add_help=False)
    base_subparser.add_argument(
        "-f",
        "--file",
        help="Pfad zur JSON-Datei für Kontaktdaten")
    base_subparser.add_argument(
        "-c",
        "--configure-only",
        action='store_true',
        help="Nur Kontaktdaten erfassen und in JSON-Datei abspeichern")
    base_subparser.add_argument(
        "-r",
        "--read-only",
        action='store_true',
        help="Es wird nicht nach fehlenden Kontaktdaten gefragt. Stattdessen wird ein Fehler angezeigt, falls benötigte Kontaktdaten in der JSON-Datei fehlen.")

    parser_search = subparsers.add_parser(
        "search", parents=[base_subparser], help="Termin suchen")
    parser_search.add_argument(
        "-s",
        "--retry-sec",
        type=int,
        default=60,
        help="Wartezeit zwischen zwei Versuchen (in Sekunden)")

    parser_code = subparsers.add_parser(
        "code",
        parents=[base_subparser],
        help="Impf-Code generieren")

    args = parser.parse_args()

    if not hasattr(args, "file") or args.file is None:
        args.file = os.path.join(PATH, "data/kontaktdaten.json")
    if not hasattr(args, "configure_only"):
        args.configure_only = False
    if not hasattr(args, "read_only"):
        args.read_only = False
    if not hasattr(args, "retry_sec"):
        args.retry_sec = 60

    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
        # parser.error terminates the program with status code 2.

    if args.command is not None:
        try:
            if args.command == "search":
                subcommand_search(args)
            elif args.command == "code":
                subcommand_code(args)
            else:
                assert False
        except ValidationError as exc:
            print(f"Fehler in {json.dumps(args.file)}:\n{str(exc)}")

    else:
        extended_settings = False

        while True:
            print(
                "Was möchtest du tun?\n"
                "[1] Termin suchen\n"
                "[2] Impf-Code generieren\n"
                f"[x] Erweiterte Einstellungen {'verbergen' if extended_settings else 'anzeigen'}\n")

            if extended_settings:
                print(
                    f"[c] --configure-only {'de' if args.configure_only else ''}aktivieren\n"
                    f"[r] --read-only {'de' if args.read_only else ''}aktivieren\n"
                    "[s] --retry-sec setzen\n")

            option = input("> Option: ").lower()
            print()

            try:
                if option == "1":
                    subcommand_search(args)
                elif option == "2":
                    subcommand_code(args)
                elif option == "x":
                    extended_settings = not extended_settings
                elif extended_settings and option == "c":
                    new_args = copy.copy(args)
                    new_args.configure_only = not new_args.configure_only
                    validate_args(new_args)
                    args = new_args
                    print(
                        f"--configure-only {'de' if not args.configure_only else ''}aktiviert.")
                elif extended_settings and option == "r":
                    new_args = copy.copy(args)
                    new_args.read_only = not new_args.read_only
                    validate_args(new_args)
                    args = new_args
                    print(
                        f"--read-only {'de' if not args.read_only else ''}aktiviert.")
                elif extended_settings and option == "s":
                    args.retry_sec = int(input("> --retry-sec="))
                else:
                    print("Falscheingabe! Bitte erneut versuchen.")
                print()
            except Exception as exc:
                print(f"\nFehler:\n{str(exc)}\n")


if __name__ == "__main__":
    print("""
                                _                 
                               (_)                
 __   __   __ _    ___    ___   _   _ __    _   _ 
 \ \ / /  / _` |  / __|  / __| | | | '_ \  | | | |
  \ V /  | (_| | | (__  | (__  | | | |_) | | |_| |
   \_/    \__,_|  \___|  \___| |_| | .__/   \__, |
                                   | |       __/ |
                                   |_|      |___/ 
""")
    print("Automatische Terminbuchung für den Corona Impfterminservice\n")

    print("Vor der Ausführung des Programms ist die Berechtigung zur Impfung zu prüfen.\n"
          "Ob Anspruch auf eine Impfung besteht, kann hier nachgelesen werden:\n"
          "https://www.impfterminservice.de/terminservice/faq\n")

    main()
