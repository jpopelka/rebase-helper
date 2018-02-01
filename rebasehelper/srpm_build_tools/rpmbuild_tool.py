# -*- coding: utf-8 -*-
#
# This tool helps you to rebase package to the latest version
# Copyright (C) 2013-2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# he Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Authors: Petr Hracek <phracek@redhat.com>
#          Tomas Hozza <thozza@redhat.com>

import os

from rebasehelper.logger import logger
from rebasehelper.build_helper import SRPMBuildToolBase, SourcePackageBuildError
from rebasehelper.utils import PathHelper
from rebasehelper.utils import ProcessHelper


class RpmbuildSRPMBuildTool(SRPMBuildToolBase):

    CMD = "rpmbuild"
    DEFAULT = True
    logs = []

    @classmethod
    def get_build_tool_name(cls):
        return cls.CMD

    @classmethod
    def is_default(cls):
        return cls.DEFAULT

    @classmethod
    def build_srpm(cls, spec, workdir, results_dir, srpm_results_dir, srpm_builder_options):
        """
        Build SRPM using rpmbuild.

        :param spec: abs path to SPEC file inside the rpmbuild/SPECS in workdir.
        :param workdir: abs path to working directory with rpmbuild directory
                        structure, which will be used as HOME dir.
        :param results_dir: abs path to dir where the log should be placed.
        :param srpm_results_dir: path to directory where SRPM will be placed.
        :param srpm_builder_options: list of additional options to rpmbuild.
        :return: abs path to built SRPM.
        """
        logger.info("Building SRPM")
        spec_loc, spec_name = os.path.split(spec)
        output = os.path.join(results_dir, "build.log")

        cmd = ['rpmbuild', '-bs', spec_name]

        if srpm_builder_options is not None:
            cmd.extend(srpm_builder_options)

        ret = ProcessHelper.run_subprocess_cwd_env(cmd,
                                                   cwd=spec_loc,
                                                   env={'HOME': workdir},
                                                   output_file=output)

        build_log_path = os.path.join(srpm_results_dir, 'build.log')

        if ret == 0:
            return PathHelper.find_first_file(workdir, '*.src.rpm')
        # An error occurred, raise an exception
        logfile = build_log_path
        cls.logs = [l for l in PathHelper.find_all_files(srpm_results_dir, '*.log')]
        raise SourcePackageBuildError("Building SRPM failed!", logfile=logfile)
