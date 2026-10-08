from zou.app.utils import auth

from zou.app.models.department import Department
from zou.app.models.person import Person

# Pre-computed once for the default test password: bcrypt per
# user per test is what made the suite slow.
_CACHED_PASSWORD_HASH = auth.encrypt_password("mypassword")


class PeopleFactories:
    """
    Users per role, persons and departments.
    """

    def generate_fixture_user(self):
        self.user = Person.create(
            first_name="John",
            last_name="Did",
            role="admin",
            email="john.did@gmail.com",
            password=_CACHED_PASSWORD_HASH,
        ).serialize()
        return self.user

    def generate_fixture_user_manager(self):
        if hasattr(self, "user_manager"):
            return self.user_manager
        self.user_manager = Person.create(
            first_name="John",
            last_name="Did2",
            role="manager",
            email="john.did.manager@gmail.com",
            password=_CACHED_PASSWORD_HASH,
        ).serialize()
        return self.user_manager

    def generate_fixture_user_cg_artist(self):
        if hasattr(self, "user_cg_artist"):
            return self.user_cg_artist
        self.user_cg_artist = Person.create(
            first_name="John",
            last_name="Did3",
            email="john.did.cg.artist@gmail.com",
            role="user",
            password=_CACHED_PASSWORD_HASH,
        ).serialize(relations=True)
        return self.user_cg_artist

    def generate_fixture_user_client(self):
        if hasattr(self, "user_client"):
            return self.user_client
        self.user_client = Person.create(
            first_name="John",
            last_name="Did4",
            role="client",
            email="john.did.client@gmail.com",
            password=_CACHED_PASSWORD_HASH,
        ).serialize()
        return self.user_client

    def generate_fixture_user_vendor(self):
        if hasattr(self, "user_vendor"):
            return self.user_vendor
        self.user_vendor = Person.create(
            first_name="John",
            last_name="Did5",
            role="vendor",
            email="john.did.vendor@gmail.com",
            password=_CACHED_PASSWORD_HASH,
        ).serialize()
        return self.user_vendor

    def generate_fixture_user_supervisor(self):
        if hasattr(self, "user_supervisor"):
            return self.user_supervisor
        self.user_supervisor = Person.create(
            first_name="John",
            last_name="Did6",
            role="supervisor",
            email="john.did.supervisor@gmail.com",
            password=_CACHED_PASSWORD_HASH,
        ).serialize()
        return self.user_supervisor

    def generate_fixture_user_supervisor_2(self):
        if hasattr(self, "user_supervisor_2"):
            return self.user_supervisor_2
        self.user_supervisor_2 = Person.create(
            first_name="John",
            last_name="Did7",
            role="supervisor",
            email="john.did.supervisor2@gmail.com",
            password=_CACHED_PASSWORD_HASH,
        ).serialize()
        return self.user_supervisor_2

    def generate_fixture_person(
        self,
        first_name="John",
        last_name="Doe",
        desktop_login="john.doe",
        email="john.doe@gmail.com",
        country=None,
    ):
        self.person = Person.get_by(email=email)
        if self.person is None:
            self.person = Person.create(
                first_name=first_name,
                last_name=last_name,
                desktop_login=desktop_login,
                email=email,
                password=_CACHED_PASSWORD_HASH,
                country=country,
            )
        return self.person

    def generate_fixture_assigner(self):
        if hasattr(self, "assigner"):
            return self.assigner
        self.assigner = Person.create(first_name="Ema", last_name="Peel")
        return self.assigner

    def generate_fixture_department(self):
        if hasattr(self, "department"):
            return self.department
        self.department = Department.create(name="Modeling", color="#FFFFFF")
        self.department_animation = Department.create(
            name="Animation", color="#FFFFFF"
        )
        return self.department
