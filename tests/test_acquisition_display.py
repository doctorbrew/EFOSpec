from efospec.acquisition_display import candidate_bounds


def test_candidate_view_tracks_offcentre_galaxies_and_target():
    galaxies=[dict(x=85.,y=110.),dict(x=240.,y=350.)]
    bounds,title=candidate_bounds((1030,1030),galaxies,dict(status='projected',pixel_xy=[130.,190.]))
    assert title=='Galaxy candidates'
    for x,y in [(85,110),(240,350),(130,190)]:
        assert bounds[0]<=x<=bounds[1] and bounds[2]<=y<=bounds[3]
    assert bounds[1]<515 and bounds[3]<515
    assert candidate_bounds((100,100),[])[0]==(-.5,99.5,-.5,99.5)
