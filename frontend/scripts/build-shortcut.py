"""Builds pwa/add-slip.shortcut, the iPhone Shortcut "Add to The Haber Process": in the share menu for images, it reads a
bet slip screenshot's text on the phone (Apple's Extract Text from Image) and opens My bets with it (/bets#slip=<text>),
where Add a bet fills in from it (frontend bets.holdSharedText). iPhones can't share to a web app, hence the Shortcut.

Rebuild (on a Mac signed in to iCloud) when the site's address changes:
    python3 scripts/build-shortcut.py https://process.jdhaber.com /tmp/unsigned.shortcut
    shortcuts sign --mode anyone --input /tmp/unsigned.shortcut --output pwa/add-slip.shortcut
"anyone" signing carries an anonymous Apple certificate ID, not the signer's name or Apple ID."""
import plistlib, sys, uuid
site = sys.argv[1]
ocr, enc = str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()
prefix = f"{site}/bets#slip="
def out(u, name): return {"Type": "ActionOutput", "OutputUUID": u, "OutputName": name}
wf = {
    "WFWorkflowClientVersion": "2607.0.2", "WFWorkflowMinimumClientVersion": 900, "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowName": "Add to The Haber Process",
    "WFWorkflowIcon": {"WFWorkflowIconStartColor": 463140863, "WFWorkflowIconGlyphNumber": 59511},
    "WFWorkflowTypes": ["ActionExtension"], "WFWorkflowInputContentItemClasses": ["WFImageContentItem"],
    "WFWorkflowHasShortcutInputVariables": True, "WFWorkflowImportQuestions": [], "WFQuickActionSurfaces": [],
    "WFWorkflowActions": [
        {"WFWorkflowActionIdentifier": "is.workflow.actions.extracttextfromimage",
         "WFWorkflowActionParameters": {"UUID": ocr, "WFImage": {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"}}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.urlencode",
         "WFWorkflowActionParameters": {"UUID": enc, "WFInput": {"Value": {"string": "￼", "attachmentsByRange": {"{0, 1}": out(ocr, "Text from Image")}},
                                                                   "WFSerializationType": "WFTextTokenString"}}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
         "WFWorkflowActionParameters": {"WFInput": {"Value": {"string": prefix + "￼",
                                                              "attachmentsByRange": {f"{{{len(prefix)}, 1}}": out(enc, "URL Encoded Text")}},
                                                    "WFSerializationType": "WFTextTokenString"}}},
    ],
}
plistlib.dump(wf, open(sys.argv[2], "wb"), fmt=plistlib.FMT_BINARY)
