# File Categorizer

A local application to organise your messy archives. It scans a given directory for files, and organizes all contained files based on various file metadata and contents.

## Requirements

- **Local First:** Requires no internet connection, scans only local files and uses only local AI models

- **Lightweight:** Runs on commodity hardware, like your personal laptop

- **Plugin Architecture:** The organization or categorization of a file is determined by various clues about a file. Clues are produced by plugins, each of which are responsible for providing clues based on specific facts about the file. Clues may include 1) metadata such as file name, directory structure, metadata (for example: EXIF data from photos), or 2) content: text (plain or OCR), people or items (in the case of photos), lyrics

- **Resumable:** the application can gracefully handle unexpected interruption, able to resume where it left off

- **Safe:** The application leaves the scanned directories and files untouched, keeping all data in a separate, locally managed database. Any filesystem writes occur in a destination directory provided by the user

- **Understandable:** produces a human digestible dashboard of the discovered organization

- **Spec Driven Development:** The application is written almost entirely by AI using spec driven development

## Extensions

- **Archive extract:** extract and scan archives as they are encountered

- **Photo metadata:** extracts and analyzes EXIF (or similar) metadata on image files

- **Encryption:** Decrypt encrypted volumes or archives, keeping track of any decryption keys that may have been discovered already. If a decryption key has not been discovered for an encountered volume, keep track of the encrypted volume for decryption and scanning later
