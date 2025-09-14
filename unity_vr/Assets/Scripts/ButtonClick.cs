using UnityEngine;
using UnityMeshImporter;

public class ButtonClick : MonoBehaviour
{
    public GameObject meshRoot;

    public void OnButtonClick()
    {
        string meshFile = "Assets/Axle shaft.ply";
        var ob = MeshImporter.Load(meshFile);
        ob.transform.SetParent(meshRoot.transform, false);
    }
}
