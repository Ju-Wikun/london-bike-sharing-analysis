from src.build_warehouse import main as build_warehouse
from src.render_dashboards import main as render_dashboards
from src.render_od_dashboards import main as render_od_dashboards


if __name__ == "__main__":
    build_warehouse()
    render_dashboards()
    render_od_dashboards()
