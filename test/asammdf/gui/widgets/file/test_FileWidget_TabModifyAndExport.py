#!/usr/bin/env python
import pathlib
from unittest import mock

from PySide6 import QtCore, QtTest, QtWidgets

from test.asammdf.gui.test_base import OpenMDF
from test.asammdf.gui.widgets.test_BaseFileWidget import TestFileWidget

# Note: If it's possible and make sense, use self.subTests
# to avoid initializing widgets multiple times and consume time.


class TestTabModifyAndExport(TestFileWidget):
    def test_lab_filter_round_trip(self):
        key = "test/natural_sort_old"
        self.addCleanup(self.settings.setValue, key, self.settings.value(key))
        self.settings.setValue(key, False)
        self.setUpFileWidget(measurement_file=self.measurement_file, default=True)
        self.widget.aspects.setCurrentIndex(1)
        self.widget.filter_view.setCurrentText("Natural sort")

        items = [self.widget.filter_tree.topLevelItem(i) for i in range(2)]
        for item in items:
            item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        names = [item.name for item in items]
        expected = {item.entry: item.name for item in items}
        labels = [item.text(0) for item in items]
        self.assertNotEqual(names, labels)

        path = pathlib.Path(self.test_workspace, "channels.lab")
        with (
            mock.patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")),
            mock.patch.object(QtWidgets.QInputDialog, "getText", return_value=("lab", True)),
        ):
            self.widget.save_filter_list()

        with self.subTest("saved channel names"):
            self.assertCountEqual(path.read_text().split("[lab]\n")[1].splitlines(), names)

        for source in ("new", "legacy"):
            with self.subTest(source):
                if source == "legacy":
                    path.write_text("[lab]\n" + "\n".join(labels))
                self.widget.clear_filter()
                self.assertEqual(self.widget._selected_filter, {})
                self.widget.load_filter_list(file_name=path)
                self.assertEqual(self.widget._selected_filter, expected)

        with self.subTest("legacy source disambiguates repeated channel names"):
            path.write_text("[lab]\ntime —— OnChange\n$CalibrationLog —— missing bus\n")
            self.widget.load_filter_list(file_name=path)
            self.assertEqual(self.widget._selected_filter, {(6, 0): "time"})

    def test_PushButton_ScrambleTexts(self):
        """
        Events:
            - Open 'FileWidget' with valid measurement.
            - Go to Tab: "Modify & Export": Index 1
            - Press PushButton "Scramble texts"
        Evaluate:
            - New file is created
            - No channel from first file is found in 2nd file (scrambled file)
        """
        # Event
        self.setUpFileWidget(measurement_file=self.measurement_file, default=True)
        channels = list(self.widget.mdf.channels_db)

        # Go to Tab: "Modify & Export": Index 1
        self.widget.aspects.setCurrentIndex(1)

        # Press PushButton ScrambleTexts
        QtTest.QTest.mouseClick(self.widget.scramble_btn, QtCore.Qt.MouseButton.LeftButton)
        self.processEvents(0.5)

        # Evaluate
        scrambled_filepath = pathlib.Path(self.test_workspace, "ASAP2_Demo_V171.scrambled.mf4")

        with OpenMDF(scrambled_filepath) as mdf_file:
            result = filter(lambda c: c in mdf_file.channels_db, channels)
            self.assertFalse(any(result))

    def test_ExportMDF(self):
        """
        When QThreads are running, event-loops needs to be processed.
        Events:
            - Open 'FileWidget' with valid measurement.
            - Go to Tab: "Modify & Export": Index 1
            - Set "channel_view" to "Natural sort"
            - Select two channels
            - Ensure that output format is MDF
            - Case 0:
                - Press PushButton Apply.
                    - Simulate that no valid path is provided.
            - Case 1:
                - Press PushButton Apply.
                    - Simulate that no valid path is provided.
        Evaluate:
            - Evaluate that file was created.
            - Open File and check that there are only two channels.
        """
        # Event
        self.setUpFileWidget(measurement_file=self.measurement_file, default=True)
        # Go to Tab: "Modify & Export": Index 1
        self.widget.aspects.setCurrentIndex(1)
        self.widget.filter_view.setCurrentText("Natural sort")

        count = 2
        selected_channels = []
        iterator = QtWidgets.QTreeWidgetItemIterator(self.widget.filter_tree)
        while iterator.value() and count:
            item = iterator.value()
            item.setCheckState(0, QtCore.Qt.CheckState.Checked)
            self.assertTrue(item.checkState(0) == QtCore.Qt.CheckState.Checked)
            selected_channels.append(item.text(0))
            iterator += 1
            count -= 1
        self.processEvents()

        # Evaluate that channels were added to "selected_filter_channels"
        for index in range(self.widget.selected_filter_channels.topLevelItemCount()):
            item = self.widget.selected_filter_channels.topLevelItem(index)
            self.assertIn(item.text(0), selected_channels)

        self.widget.output_format.setCurrentText("MDF")

        # Case 0:
        self.processEvents()
        with self.subTest("test_ExportMDF_0"):
            with (
                mock.patch("asammdf.gui.widgets.file.QtWidgets.QFileDialog.getSaveFileName") as mc_getSaveFileName,
                mock.patch("asammdf.gui.widgets.file.setup_progress") as mo_setup_progress,
            ):
                mc_getSaveFileName.return_value = None, None
                QtTest.QTest.mouseClick(self.widget.apply_btn, QtCore.Qt.MouseButton.LeftButton)
                self.processEvents()
            # Evaluate
            # Progress is not created
            mo_setup_progress.assert_not_called()

        # Case 1:
        self.processEvents()
        with self.subTest("test_ExportMDF_1"):
            saved_file = pathlib.Path(self.test_workspace, f"{self.id()}.mf4")
            with mock.patch("asammdf.gui.widgets.file.QtWidgets.QFileDialog.getSaveFileName") as mc_getSaveFileName:
                mc_getSaveFileName.return_value = str(saved_file), None
                QtTest.QTest.mouseClick(self.widget.apply_btn, QtCore.Qt.MouseButton.LeftButton)
                self.processEvents(1)
        # Wait for thread to finish
        self.processEvents(1)

        # Evaluate
        self.assertTrue(saved_file.exists())

        # TearDown Widget
        with OpenMDF(saved_file) as mdf_file:
            for sig in mdf_file.iter_channels():
                self.assertIn(sig.name, selected_channels)
