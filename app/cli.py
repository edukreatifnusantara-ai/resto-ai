from app.database import init_db


def main() -> None:
    init_db()
    print("Database siap: DATA DUMMY / SIMULASI")


if __name__ == "__main__":
    main()
