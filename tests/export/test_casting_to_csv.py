from tests.base import ApiDBTestCase


class CastingCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super(CastingCsvExportTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project.update({"production_type": "tvshow"})
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()

    def test_import_casting(self):
        project_id = str(self.project.id)
        mp_id = self.generate_fixture_main_pack_episode(project_id).id
        for name, asset_type_id in [
            ("Lake", self.asset_type_environment.id),
            ("Mine", self.asset_type_environment.id),
            ("Boat", self.asset_type_props.id),
            ("Pool", self.asset_type_props.id),
            ("Flowers", self.asset_type_props.id),
            ("Block", self.asset_type_props.id),
            ("Wagon", self.asset_type_props.id),
            ("Victor", self.asset_type_character.id),
            ("John", self.asset_type_character.id),
        ]:
            self.generate_fixture_asset(
                name, asset_type_id=asset_type_id, episode_id=mp_id
            )
            if name == "Lake":
                self.asset_lake_id = self.asset.id
            if name == "Mine":
                self.asset_mine_id = self.asset.id

        self.generate_fixture_episode("E01")
        self.generate_fixture_sequence("SEQ01")
        self.generate_fixture_shot("SH01").id
        self.generate_fixture_shot("SH02").id
        self.generate_fixture_sequence("SEQ02")
        self.generate_fixture_shot("SH01").id
        episode2_id = self.generate_fixture_episode("E02").id
        self.generate_fixture_sequence("SEQ01")
        self.generate_fixture_shot("SH01").id

        path = "/import/csv/projects/%s/casting" % project_id
        self.upload_csv(path, "casting")

        self.maxDiff = None

        path = "/export/csv/projects/%s/casting.csv" % project_id
        csv = self.get_raw(path)
        self.assertTrue("MP;Environment;Lake;Props;Boat;1;setdress" in csv)
        self.assertFalse("E01;SEQ01;SH01;Character;John;1;animate" in csv)
        self.assertFalse("Episode;E01;Character;John;1;animate" in csv)

        path = (
            "/export/csv/projects/%s/casting.csv?is_shot_casting=true"
            % project_id
        )
        csv = self.get_raw(path)
        self.assertTrue("E01;SEQ01;SH01;Character;John;1;animate" in csv)
        self.assertFalse("MP;Environment;Lake;Props;Boat;1;setdress" in csv)
        self.assertTrue("E02;SEQ01;SH01;Character;Victor;1;animate" in csv)
        self.assertFalse("Episode;E01;Character;John;1;animate" in csv)

        path = (
            "/export/csv/projects/%s/casting.csv?is_shot_casting=true&episode_id=%s"
            % (project_id, episode2_id)
        )
        csv = self.get_raw(path)
        self.assertFalse("E01;SEQ01;SH01;Character;John;1;animate" in csv)
        self.assertFalse("MP;Environment;Lake;Props;Boat;1;setdress" in csv)
        self.assertTrue("E02;SEQ01;SH01;Character;Victor;1;animate" in csv)
        self.assertFalse("Episode;E01;Character;John;1;animate" in csv)

        path = (
            "/export/csv/projects/%s/casting.csv?episode_id=all" % project_id
        )
        csv = self.get_raw(path)
        print(csv)
        self.assertFalse("E01;SEQ01;SH01;Character;John;1;animate" in csv)
        self.assertFalse("MP;Environment;Lake;Props;Boat;1;setdress" in csv)
        self.assertTrue("Episode;E01;Character;John;1;animate" in csv)
