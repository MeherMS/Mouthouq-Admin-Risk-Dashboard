import argparse

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Customer
from app.synthetic.config import FULL, SMALL
from app.synthetic.population import generate_population, reset_synthetic_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic customers and stores.")
    parser.add_argument("--full", action="store_true", help="Use full size (10k customers, 500 stores).")
    parser.add_argument("--reset", action="store_true", help="Delete existing synthetic data first.")
    args = parser.parse_args()

    cfg = FULL if args.full else SMALL

    with SessionLocal() as session:
        existing = session.scalar(select(func.count()).select_from(Customer))
        if existing and not args.reset:
            print(f"Database already has {existing} customers. Re-run with --reset to regenerate.")
            return

        if args.reset:
            reset_synthetic_data(session)

        customers, stores = generate_population(session, cfg)
        session.commit()

    print(f"Created {len(customers)} customers and {len(stores)} stores (seed={cfg.seed}).")
    print("Customer profiles:")
    print(customers["profile"].value_counts().to_string())
    print("Store profiles:")
    print(stores["profile"].value_counts().to_string())
    n_clusters = customers["cluster_id"].dropna().nunique()
    print(f"Fraud clusters: {n_clusters}")


if __name__ == "__main__":
    main()